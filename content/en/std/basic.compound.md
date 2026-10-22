---
title: Compound types
summary: "The eight kinds of types constructed from other types; how a pointer value records which object it points to besides an address, and what a pointer can still do after its storage is released; which objects are pointer-interconvertible, and how far std::launder can reach."
updated: 2026-10-19
---

!!! tldr
    - There are eight kinds of compound types: arrays, functions, pointers, references, classes, unions, enumerations and pointers to members. Constructing a type whose size exceeds `SIZE_MAX` bytes is ill-formed.
    - A pointer value is not just an address: a past-the-end pointer does not point to another object that happens to be at that address, even if they compare equal.
    - After storage is released, pointers to it can still be copied and passed around; dereferencing is UB, and comparison and boolean conversion are implementation-defined.
    - The same object, a union and its members, and a standard-layout class and its first member or base class subobjects are pointer-interconvertible, and can be obtained from one another with `reinterpret_cast`. An array and its first element are not.
    - `std::launder` can switch a pointer to another object at the same address, but cannot widen the range of bytes reachable through the pointer.

**Compound types** are types constructed from other types. The first two paragraphs of [[basic.compound]] (6.9.5) are just a directory; the details of each compound type are spread over declarators [[dcl.decl]], classes [[class]], enumerations [[dcl.enum]] and so on. The body of this subclause is about pointers (¶3–¶9): what exactly a pointer value is, when it can still be used, and which objects can be converted to one another with `reinterpret_cast`. The pointer-related UB in [[basic.life]], [[expr.add]], [[expr.reinterpret.cast]] and `std::launder` ([[ptr.launder]]) all starts from the definitions here.

## Eight kinds of compound types (¶1–¶2)

| ¶ | Compound type | Detailed rules | Primary category trait |
|---|---|---|---|
| 1.1 | arrays of objects of a given type | [[dcl.array]] | `is_array` |
| 1.2 | functions, which have parameters of given types and return `void` or a result of a given type | [[dcl.fct]] | `is_function` |
| 1.3 | pointers to cv `void`, objects or functions (including static members of classes) | [[dcl.ptr]] | `is_pointer` |
| 1.4 | references to objects or functions, either lvalue or rvalue references | [[dcl.ref]] | `is_lvalue_reference`, `is_rvalue_reference` |
| 1.5 | classes, containing a sequence of members and restricting access to them | [[class]], [[class.access]] | `is_class` |
| 1.6 | unions, classes capable of containing objects of different types at different times | [[class.union]] | `is_union` |
| 1.7 | enumerations, comprising a set of named constant values | [[dcl.enum]] | `is_enum` |
| 1.8 | pointers to non-static class members | [[dcl.mptr]] | `is_member_object_pointer`, `is_member_function_pointer` |

Classes, unions and enumerations are not intuitively "constructed from other types", but the standard classifies them as compound types too: whatever is not a fundamental type is a compound type, and `is_compound_v<T>` is just `!is_fundamental_v<T>`.

A pointer to a static member is an ordinary pointer (footnote 26): `&S::static_member` has type `int*`, not `int S::*`. Pointers to data members and pointers to member functions are collectively the **pointer-to-member types**.

¶2 These methods of constructing types can be applied recursively, with the restrictions in [[dcl.meaning]]: no arrays of references, no pointers to references, functions cannot return arrays or functions, and so on. In addition, constructing a type whose object representation exceeds the maximum value of `std::size_t` bytes makes the program ill-formed:

```cpp run error
#include <cstdint>
using Huge = char[SIZE_MAX][2];   // error: the type's size exceeds SIZE_MAX
```

What is ill-formed is constructing the type itself, without waiting for an object of it to be defined. The result type of `sizeof` is `size_t` ([[expr.sizeof]]), and a type whose size doesn't fit in `size_t` couldn't even have its `sizeof` evaluated.

## A pointer value is more than an address (¶3)

```cpp run ub
#include <cstdio>

int main() {
  int a = 1, b = 2;
  int* p = &a + 1;           // the past-the-end pointer of a
  if (p == &b) {             // unspecified result: may be true
    *p = 10;                 // UB: p is a past-the-end pointer and does not point to b
  }
  std::printf("%d\n", b);
}
```

`b` may happen to immediately follow `a`, in which case `p == &b` is true. Even so, `*p = 10` does not validly modify `b`.

### Four kinds of pointer value

¶3 specifies that every value of pointer type is one of the following:

| Kind | Example | What it can do |
|---|---|---|
| ¶3.1 a pointer to an object or function | `&x`, `new int`, `&f` | dereference, arithmetic, comparison |
| ¶3.2 a pointer past the end of an object | `arr + N`, `&x + 1` | arithmetic, comparison; no dereference |
| ¶3.3 the null pointer value for that type | `nullptr`, `int* p{}` | comparison, boolean conversion |
| ¶3.4 an invalid pointer value | the result of certain conversions ([[expr.reinterpret.cast#5]]) | almost nothing |

A pointer to an object and a past-the-end pointer both **represent an address**: respectively the address of the first byte the object occupies, and the address of the first byte after the end of the object's storage. For an object not within its lifetime, it is the first byte it will occupy or used to occupy (footnote 27).

Note 2 is the key to this subclause: a pointer past the end of an object is not considered to point to an unrelated object of the same type that happens to be at that address. So the same address can correspond to different pointer values. Besides the address, a pointer value records which object it came from; this is usually called **pointer provenance**. Compilers' alias analysis relies on it: a write through `&a + 1` can be assumed not to change `b`.

### A single object is treated as a one-element array

¶3 also gives two "treated as" rules for pointer arithmetic ([[expr.add]]) and comparison ([[expr.rel]], [[expr.eq]]):

1. a pointer past the end of the last element of an array `x` of `n` elements is treated as pointing to a hypothetical element `x[n]`;
2. an object of type `T` that is not an array element is treated as an element of an array of one `T`.

The second rule makes `&x + 1` valid: it is the past-the-end pointer of `x`. So treating a single object as a range of length 1, as in `std::copy(&x, &x + 1, out)`, works.

### Terms and representation

The beginning of ¶3 defines some names. The type of a pointer to cv `void` or to an object type is an **object pointer type**. Note 1 points out that `void*` is an object pointer type but not a pointer to an object type, since `void` is not an object type. The type of a pointer that can designate a function is a **function pointer type**. Except for pointers to static members, "pointer" in the standard never includes pointers to members. Pointers to incomplete types are allowed, though there is little they can do ([[basic.types.general]]).

The value representation of pointer types is implementation-defined. Pointers to layout-compatible types ([[basic.types.general#9]]) must have the same value representation and alignment requirements. Note 3 adds that pointers to over-aligned types ([[basic.align]]) have no special representation; their range of valid values is merely restricted by the alignment requirement, for example the low bits must be zero.

!!! impl
    On mainstream platforms, object pointers and function pointers are both a machine-word address, but the standard deliberately does not require this. Historically there were machines with segmented memory and word addressing (`char*` wider than `int*`). On today's CHERI architecture, a pointer is a 128-bit capability carrying bounds and permissions; AArch64 pointer authentication (PAC) and memory tagging (MTE) also put non-address information in a pointer's high bits.

## Pointers after storage is released (¶6)

```cpp run impl
#include <cstdlib>

int main() {
  int* p = static_cast<int*>(std::malloc(sizeof(int)));
  std::free(p);              // the duration of the storage p points to ends
  int* q = p;                // OK: copying the pointer value is unrestricted
  if (q) { }                 // implementation-defined: boolean conversion
  bool same = (p == q);      // implementation-defined: equality comparison
  // *p = 1;                 // UB: indirection
  return same ? 0 : 1;
}
```

¶6 first defines: a pointer value `P` is [[g:valid-in-the-context-of|valid in the context of an evaluation]] `E` if `P` is a pointer to a function or a null pointer value, or if it points to or past the end of an object `O` and `E` occurs within the duration of the region of storage for `O` (after it begins, before it ends).

If a pointer value that is not valid in the context of an evaluation `E` is used in `E`:

- ¶6.1 if `E` is an indirection (`*P`, [[expr.unary.op]]), the behavior is undefined;
- ¶6.2 if `E` is a boolean conversion ([[conv.bool]]), or is performed by unary `+`, addition or subtraction, or a three-way comparison, relational or equality operator, the behavior is implementation-defined.

Copying such a pointer value, passing it as an argument, or storing it in a variable are unrestricted.

Note 6 adds that `P` can be valid even if the type it points to is unrelated to `O`, or `O` is not within its lifetime; such pointers are further restricted by [[basic.life]], [[basic.lval]] and [[expr.add]]. In other words, validity only cares whether the storage still exists, not whether the object is alive or the type matches.

### Differences from C++23

This is new wording after C++23. C++23's [basic.stc.general] paragraph 4 said that when the duration of a region of storage ends, the values of all pointers representing the address of any part of it become invalid pointer values; indirection through an invalid pointer value, or passing it to a deallocation function, was UB; and any other use, including merely copying it, was implementation-defined.

This model of collectively rewriting pointer values at deallocation had two problems. First, a great deal of real code depended in theory on implementation-defined behavior; for example, comparing a pointer that might already have been freed in a lock-free data structure, where even copying it was not safe. Second, it was counterintuitive: how could a variable's value change because another thread called `free`?

In the new model, the pointer value itself does not change; validity becomes a relation between a pointer value and an evaluation. Correspondingly, [[basic.stc.general]] now only says that the use of pointers to the storage after its duration ends is restricted. The accompanying [[expr.assign#2.2]] specifies that assigning a pointer value that is invalid in the current context to a volatile pointer glvalue is treated as converting it to `std::uintptr_t` and back first.

## Pointers before the storage duration begins (¶5)

¶5 If an evaluation produces a pointer value that points to or past the end of an object `O`, or causes some object to have such a value ([[basic.types.trivial]]), and the evaluation happens before the duration of the region of storage for `O` begins, the behavior is undefined.

Note 5 explains that relaxed atomic operations may produce such values, while conversions from integers to pointers do not ([[expr.reinterpret.cast#5]] chooses a value that gives the program defined behavior). This rule targets out-of-thin-air values in the memory model: under the formal model of relaxed atomics, an execution with reversed causality, where one thread reads a pointer to storage not yet allocated, is theoretically possible. ¶5 makes such executions UB, excluding them from the valid executions that must be considered.

## Pointers to string literals (¶4)

```cpp run error
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";  // error: the two literals may or may not share storage
constexpr bool b2 = f() == f();       // error: each evaluation may produce a different object
constexpr const char* p = f();
constexpr bool b3 = p == p;           // OK: the same pointer value, true
constexpr bool b4 = +"foo" == +"bar"; // OK: false, the contents differ, so they cannot overlap
```

String literal objects, the backing arrays of `initializer_list`s and template parameter objects are all **potentially non-unique objects** ([[intro.object#9]]): the implementation may merge or overlap their storage; for example `"foo"` and `"xfoo"` may share a suffix. At run time this only makes comparison results unspecified; but constant evaluation must give a definite answer.

¶4 A pointer value pointing to a potentially non-unique object `O` is **associated with** the evaluation that produced it:

- ¶4.1 the evaluation of the *string-literal* that resulted in the string literal object;
- ¶4.2 the evaluation of the initializer list that resulted in the backing array;
- ¶4.3 the initialization of the template parameter object that is or contains `O` ([[temp.arg.nontype]], [[meta.define.static]]).

Note 4 adds that a pointer obtained by pointer arithmetic from a pointer associated with an evaluation `E` is also associated with `E`. On this basis [[expr.const.core]] specifies that comparing two pointers associated with different evaluations that could point to the same position in the same potentially non-unique object is not a core constant expression. That is why `b1` and `b2` above are rejected.

## Pointer-interconvertibility (¶7)

```cpp run ok
#include <cstdio>

struct S { int a; double b; };    // standard-layout
union U { int i; float f; };
struct Base { int x; };
struct Der : Base { };            // standard-layout: all data members are in Base

int main() {
  S s{1, 2.0};
  int* pa = reinterpret_cast<int*>(&s);    // OK: pa points to s.a
  S*   ps = reinterpret_cast<S*>(pa);      // OK: and back again
  U u{.i = 3};
  int* pi = reinterpret_cast<int*>(&u);    // OK: a union object and its member
  Der d{};
  Base* pb = reinterpret_cast<Base*>(&d);  // OK, though static_cast is more appropriate
  std::printf("%d %g %d %d\n", *pa, ps->b, *pi, pb->x);
}
```

¶7 Two objects *a* and *b* are [[g:pointer-interconvertible|pointer-interconvertible]] if:

- ¶7.1 they are the same object;
- ¶7.2 one is a union object and the other is a non-static data member of it ([[class.union]]);
- ¶7.3 one is a standard-layout class object and the other is its first non-static data member or any base class subobject of it ([[class.mem]]);
- ¶7.4 there exists an object *c* such that *a* and *c* are pointer-interconvertible, and *c* and *b* are pointer-interconvertible.

Two pointer-interconvertible objects have the same address, and a pointer to one can be obtained from a pointer to the other with `reinterpret_cast`. The mechanism is in [[expr.static.cast#12]]: when converting from `void*` to `T*`, if the original pointer points to an object *a* and there is an object *b* of type similar to `T` that is pointer-interconvertible with *a*, the result points to *b*; otherwise the pointer value is unchanged and still points to *a*. `reinterpret_cast` between object pointers is defined this way.

!!! std
    An array object and its first element are not pointer-interconvertible, even though they have the same address.

Note 7: an array object and its first element have the same address but are not pointer-interconvertible.

When the conditions are not met, the converted pointer still points to the original object, and accessing through it is usually UB:

```cpp run ub
struct NS {                     // not standard-layout: different access control
  int a;
private:
  int b = 0;
public:
  int get() const { return b; }
};

int main() {
  NS ns{};
  int* p = reinterpret_cast<int*>(&ns);  // still points to ns, not to ns.a
  int r = *p;                            // UB: accesses an NS object through an int glvalue

  int arr[2] = {1, 2};
  int (*pa)[2] = reinterpret_cast<int(*)[2]>(&arr[0]);  // still points to arr[0]
  int s = (*pa)[1];                      // UB: there is no int[2] object at arr[0]
  return r + s + ns.get();
}
```

Both pieces of code work in practice, because the addresses really are the same. But the compiler is entitled to do alias analysis on the basis that `p` points to an `NS`, not an `int`. The right way is to take `&ns.a` directly, or let `arr` undergo array-to-pointer conversion to get a pointer to the first element.

Why aren't an array and its first element interconvertible? If they were, an `int*` could be converted into a pointer to the whole array, and `arr[1]` accessed from there. The compiler could no longer assume that an `int*` can only access the array it is in. The next section and `std::launder` are designed around exactly this reachable range.

!!! note "Related traits"
    C++20 provides `std::is_pointer_interconvertible_base_of<B, D>` and `std::is_pointer_interconvertible_with_class(&C::m)` ([[meta.rel]], [[meta.member]]). The libc++ shipped with Clang 23 does not provide them yet; Clang has the builtin `__is_pointer_interconvertible_base_of(B, D)`.

## Bytes reachable through a pointer (¶8)

¶8 Let a pointer value point to an object *x*. A byte of storage *b* is [[g:reachable-through|reachable through]] the pointer value if there is an object *y*, pointer-interconvertible with *x*, such that *b* is within the storage occupied by *y*, or within the immediately-enclosing array object if *y* is an array element.

This definition is used only for the precondition of `std::launder` ([[ptr.launder#2]]): all bytes reachable through the result must be reachable through the argument pointer. `launder` can switch a pointer to another object at the same address, but cannot widen the range of memory that can be accessed. Otherwise compilers' escape analysis would break down: a function given only `&s.a[0]` could use `launder` to widen its access to all of `s`.

```cpp run ok
#include <new>

int main() {
  int arr[2] = {1, 2};
  // &arr[0] is an array element, so the whole immediately-enclosing arr is reachable
  int (*pa)[2] = std::launder(reinterpret_cast<int(*)[2]>(&arr[0]));   // OK
  return (*pa)[1] == 2 ? 0 : 1;
}
```

```cpp run ub
#include <new>

struct S2 { int a[2]; int b; };

int main() {
  S2 s{{1, 2}, 3};
  // &s.a[0] can reach only the bytes of s.a; s.b is not reachable
  S2* p = std::launder(reinterpret_cast<S2*>(&s.a[0]));   // UB: violates the precondition
  return p->b;
}
```

## `void*` (¶9)

¶9 A pointer to cv `void` can point to objects of unknown type, and must be able to hold any object pointer. `void*` has the same representation and alignment requirements as `char*`.

The latter is inherited from C: before C introduced `void*`, `char*` served as the generic pointer and `malloc` returned `char*`. `void*` is guaranteed to hold only object pointers, not function pointers. Conversion between function pointers and `void*` is **conditionally-supported** (an implementation may not support it, but must diagnose if it doesn't, [[expr.reinterpret.cast]]); POSIX's `dlsym` additionally requires it to work.

## Other compound types at a glance

| Type | Key points | Details |
|---|---|---|
| arrays `T[N]`, `T[]` | the element type must be an object type; cv-qualification applies to the elements ([[basic.type.qualifier#3]]) | [[dcl.array]] |
| functions `R(Args...)` | top-level cv on parameters is dropped, array and function parameters are adjusted to pointers; since C++17 `noexcept` is part of the function type | [[dcl.fct]] |
| references `T&`, `T&&` | not objects, no cv-qualification; reference collapsing; no references to references, arrays of references or pointers to references | [[dcl.ref]] |
| classes, unions | properties like standard-layout and trivially copyable are in [[class.prop]] | [[class]] |
| enumerations | scoped or unscoped; representation determined by the underlying type ([[basic.fundamental#6]]) | [[dcl.enum]] |
| pointers to members `T C::*` | not pointers; cannot point to static members or reference members; have a null member pointer value | [[dcl.mptr]], [[expr.mptr.oper]] |

!!! impl "Representation of pointers to members"
    - Itanium ABI: a pointer to data member is the member's byte offset within the class, with the null value represented as `-1`, since offset 0 is a valid first member. A pointer to member function takes two words: one is the function address (for a virtual function, the vtable offset plus 1), the other the `this` adjustment; the ARM variant uses the lowest bit of the adjustment as the virtual flag instead.
    - MSVC: the size of a pointer to member function depends on the class's inheritance model. With single inheritance it is the size of an ordinary pointer; multiple and virtual inheritance need more adjustment fields. For incomplete types the most conservative model is used by default, which can be controlled with the `/vmg` and `/vmb` options or keywords like `__single_inheritance`.

## Common misconceptions

!!! pitfall "If `p == q` is true, `p` and `q` are interchangeable"
    Equality comparison compares only addresses ([[expr.eq]]), while a pointer value also carries information about which object it points to. A past-the-end pointer and a pointer to the next object, or a pointer to an old object and a pointer to a new object at the same place ([[basic.life]]), may compare equal but are not interchangeable.

!!! pitfall "`reinterpret_cast` changes the object a pointer points to"
    For objects that are not pointer-interconvertible, the pointer obtained by `reinterpret_cast<T*>(p)` still points to the original object; only the type changed. Whether later accesses are valid is decided by [[basic.lval#11]], and they are usually UB.

## Questions

!!! question "1. Given `struct A { int x; }; struct B : A { }; struct C : B { };`, is a `C` object pointer-interconvertible with its member `x`?"

<details markdown="1">
<summary>Answer</summary>

Yes. `C` is a standard-layout class, with all data members first declared in the single class `A`. By ¶7.3, a `C` object is pointer-interconvertible with its base class subobjects `B` and `A`; the `A` subobject is an object of a standard-layout class and is pointer-interconvertible with its first non-static data member `x`; and by the transitivity of ¶7.4, the `C` object is pointer-interconvertible with `x`. So `reinterpret_cast<int*>(&c)` points to `c.x`.
</details>

!!! question "2. Why does ¶6 make `if (p)` implementation-defined, rather than UB like `*p`, or simply well-defined?"

<details markdown="1">
<summary>Answer</summary>

It isn't well-defined because on some architectures loading an invalid address into an address register may trap, and after storage is released its address space may be remapped; the standard cannot require every implementation to give a meaningful result.

It isn't UB because a lot of real code (comparisons in lock-free algorithms, debug assertions, logging) still checks or compares pointers after the storage is released. If all of that were UB, compilers would be entitled to delete such code. Implementation-defined is the compromise: on mainstream implementations it is just an address comparison, and implementations must document it.
</details>

!!! question "3. Is `int a[2][2]{}; int* p = &a[0][0]; p[3] = 1;` valid?"

<details markdown="1">
<summary>Answer</summary>

No, it is UB. `p` points to the element `a[0][0]` of `a[0]` (an `int[2]`). Per [[expr.add]], `p + 2` is the past-the-end pointer of `a[0]`, and `p + 3` is already beyond that array, so the pointer arithmetic itself is UB. Although `a[1][1]` happens to be at that address, the rule that a past-the-end pointer does not point to an unrelated object (note 2 in ¶3), together with the array bounds of [[expr.add]], forbids treating a multidimensional array as a one-dimensional one. `std::launder` cannot fix it either, because the only bytes reachable through `&a[0][0]` are those of `a[0]`.
</details>
