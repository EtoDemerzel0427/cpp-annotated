---
title: dynamic_cast
summary: "The only conversion that checks an object's actual type at run time: when it can be written, which cases are done at compile time, how downcasts and cross-casts are checked, what a failure gives, and how it behaves during construction, in constant evaluation and at the ABI level."
updated: 2026-10-19
---

!!! tldr
    - `dynamic_cast` looks at the object's actual type at run time; on success it gives a pointer or reference to the target subobject, and on failure the pointer form gives a null pointer while the reference form throws `std::bad_cast`.
    - Upcasts and same-type conversions are done at compile time and need no virtual functions; all other cases require the operand to be of polymorphic type, i.e. a class with at least one virtual function.
    - The runtime check only follows public inheritance paths; it can downcast, and it can also do cross-casts and downcasts from virtual bases, which `static_cast` can't.
    - The pointer given to `dynamic_cast` must point to a live object; a dangling pointer is undefined behavior, not a safe null result.
    - In a base class's constructor and destructor, the object is treated as the base class itself, so conversions to the derived class always fail.

## A checked downcast

```cpp run title="dyn-intro.cpp" ok
struct Shape { virtual ~Shape() = default; };
struct Circle : Shape { int r = 1; };
struct Square : Shape {};

int radius(Shape* s) {
  if (auto* c = dynamic_cast<Circle*>(s))
    return c->r;          // s really points to a Circle
  return 0;               // not a Circle: null pointer
}

int main() {
  Circle c;
  Square q;
  return radius(&c) == 1 && radius(&q) == 0 ? 0 : 1;
}
```

`static_cast<Circle*>(s)` also compiles, but it trusts the programmer: when `s` actually points to a `Square`, the result is simply a wrong pointer. `dynamic_cast` looks at the **dynamic type** of `*s` at run time (the object's actual type, as opposed to the expression's static type) and checks whether there really is a `Circle` in it.

This check is possible because `Shape` has a virtual function. A class with virtual functions is a **polymorphic class** ([[class.virtual]]); its objects store a pointer to a vtable, and the vtable holds type information (RTTI). A class without virtual functions has no such information in its objects, so `dynamic_cast` has nothing to check.

## What can be written (¶1, ¶2, ¶5)

¶1 The `T` in `dynamic_cast<T>(v)` must be one of:

- a pointer or reference to a complete class type;
- a pointer to (possibly cv-qualified) `void`.

`dynamic_cast` also can't cast away `const` or `volatile` ([[expr.const.cast#6]]); add a `const_cast` on top if needed.

¶2 The form of the operand must correspond to `T`, and the value category of the result follows:

| `T` | Operand `v` | Result |
|---|---|---|
| Pointer type | A prvalue pointer to a complete class type | prvalue |
| Lvalue reference `C&` | An lvalue of complete class type | lvalue |
| Rvalue reference `C&&` | A glvalue of complete class type | xvalue |

The rvalue reference form also accepts a prvalue operand: a prvalue used as an operand first undergoes [[g:temporary-materialization-conversion|temporary materialization]] into an xvalue ([[basic.lval#7]]).

¶5 Apart from the two cases in the next section, `v` must be a pointer to or glvalue of a polymorphic type.

```cpp title="dyn-requirements.cpp" error
struct V { virtual ~V() = default; };
struct D : V {};
struct Inc;
struct N {};
struct M : N {};

void f(const V* cv, V* v, N* n, Inc* pi) {
  dynamic_cast<D*>(cv);        // error: casts away const
  dynamic_cast<const D*>(cv);  // OK
  dynamic_cast<int*>(v);       // error: int is not a class type
  dynamic_cast<D>(*v);         // error: T must be a pointer or reference
  dynamic_cast<M*>(n);         // error: N is not polymorphic (¶5)
  dynamic_cast<D&>(V{});       // error: an lvalue reference requires an lvalue
  dynamic_cast<D&&>(V{});      // OK: the prvalue is materialized first
  dynamic_cast<Inc*>(v);       // error: the target class is incomplete
  dynamic_cast<V*>(pi);        // error: the operand points to an incomplete class
}
```

## Cases done at compile time (¶3, ¶4)

¶3 If the type of `v` is the same as `T` (ignoring cv-qualification), the result is `v`, with cv-qualification added if necessary.

¶4 For a conversion from a derived class to a base class, an **upcast**, the result points to the unique `B` subobject of the `D` object pointed to by `v`; if `v` is null, the result is null. References are the same. If `B` is an inaccessible or ambiguous base of `D`, the program is ill-formed.

```cpp run title="dyn-upcast.cpp" ok
struct B {};
struct D : B {};

void foo(D* dp) {
  B* bp = dynamic_cast<B*>(dp);   // equivalent to B* bp = dp;
  (void)bp;
}

int main() { D d; foo(&d); }
```

This is Example 1 in the standard. `B` doesn't need virtual functions, because an upcast is exactly the same as the implicit conversion and the offset can be computed at compile time. The point of this rule is to let generic code write `dynamic_cast` in both directions.

Footnote 45 adds one thing: the complete object containing `v` may have other `B` subobjects, but they aren't considered; an upcast starts only from `v`'s static type `D`.

## The runtime check (¶6–¶10)

### Null and dangling pointers (¶6, ¶7)

¶6 If `v` is a null pointer value, the result is a null pointer value.

¶7 `v` must point to an object whose type is [[g:similar-types|similar]] to the type pointed to by `v` and that is within its lifetime or under construction or destruction; otherwise the behavior is undefined. The same applies to glvalue operands.

```cpp run title="dyn-dangling.cpp" ub
struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  B* p = new D;
  delete p;
  D* d = dynamic_cast<D*>(p);   // UB: *p is no longer within its lifetime
  return d != nullptr;
}
```

`dynamic_cast` first has to read the vtable pointer in the object, but by then the memory has been freed and the vtable pointer no longer exists. In our tests AddressSanitizer reports heap-use-after-free on this line. So `dynamic_cast` can't be used to check whether a pointer is still valid, nor on a wrongly typed pointer obtained through `reinterpret_cast` (see [[basic.life#7]]).

### Recovering the whole object: conversion to `void*` (¶8)

¶8 If `T` is a pointer to `void`, the result points to the **most derived object** pointed to by `v` (the complete object that is not a subobject of any other object, [[intro.object]]).

```cpp run title="dyn-void.cpp" ok
struct A { virtual ~A() = default; int a; };
struct B { virtual ~B() = default; int b; };
struct D : A, B {};

int main() {
  D d;
  B* pb = &d;                          // points to the B subobject
  void* whole = dynamic_cast<void*>(pb);
  return whole == static_cast<void*>(&d)
      && static_cast<void*>(pb) != whole ? 0 : 1;
}
```

With multiple inheritance, the `B` subobject is not at the start address of `d`. `static_cast<void*>(pb)` only changes the type and keeps the address; only `dynamic_cast<void*>(pb)` recovers the start of the whole object. When you need to decide by address whether two base class pointers point to the same object, this is the only portable way.

### The checking algorithm (¶8, ¶9)

All other cases need a runtime check. Let `C` be the class pointed to or referred to by `T`; the check specified in paragraph 9 logically has three steps:

1. ¶9.1 **Downcast**: if, in the most derived object containing `v`, `v` points to a public base class subobject of a `C` object, and only one `C` object is derived from the subobject pointed to by `v`, the result points to that `C` object.
2. ¶9.2 **Cross-cast**: otherwise, if `v` points to a public base class subobject of the most derived object, and the type of the most derived object has an unambiguous public base class `C`, the result points to that `C` subobject of the most derived object.
3. ¶9.3 Otherwise the check fails.

The first step starts from the subobject pointed to by `v` and searches in the derived direction along the inheritance chain that contains it. The second step first goes to the most derived object and then looks for a unique public `C` in the whole object, so it can move to another branch of the hierarchy. Both steps only recognize public inheritance: private inheritance relationships are invisible at run time.

```cpp run title="dyn-cross.cpp" ok
struct Shape { virtual ~Shape() = default; };
struct Drawable {
  virtual ~Drawable() = default;
  virtual int draw() const = 0;
};
struct Circle : Shape, Drawable {
  int draw() const override { return 1; }
};
struct Square : Shape {};

int main() {
  Circle c;
  Square s;
  Shape* p1 = &c;
  Shape* p2 = &s;
  auto* down = dynamic_cast<Circle*>(p1);    // ¶9.1: succeeds
  auto* side = dynamic_cast<Drawable*>(p1);  // ¶9.2: succeeds
  auto* none = dynamic_cast<Drawable*>(p2);  // fails: null pointer
  return down == &c && side && side->draw() == 1
      && none == nullptr ? 0 : 1;
}
```

`Shape` and `Drawable` have no inheritance relationship, so `static_cast<Drawable*>(p1)` is ill-formed; `reinterpret_cast` compiles, but the resulting pointer doesn't point to the `Drawable` subobject. Only `dynamic_cast` can do a cross-cast.

### The result of failure (¶10)

¶10 If a conversion to a pointer type fails, the result is the null pointer value of the target type. If a conversion to a reference type fails, an exception of a type that would match a handler of type `std::bad_cast` ([[bad.cast]]) is thrown, because references have no null value to use.

```cpp run title="dyn-bad-cast.cpp" ok
#include <typeinfo>

struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  B b;
  try {
    D& d = dynamic_cast<D&>(b);   // b is not a D: throws std::bad_cast
    (void)d;
    return 1;
  } catch (const std::bad_cast&) {
    return 0;
  }
}
```

### Private inheritance, virtual bases and duplicate subobjects

Example 2 in the standard puts these edge cases together. Below is a compilable adaptation, with the two lines from the original that are ill-formed or throw turned into comments:

```cpp run title="dyn-std-example.cpp" ok
class A { virtual void f() {} };
class B { virtual void g() {} };
class D : public virtual A, private B {};

void g() {
  D  d;
  B* bp = (B*)&d;                // a C-style cast can ignore private inheritance
  A* ap = &d;                    // public derivation, no cast needed
  // D& dr = dynamic_cast<D&>(*bp);  // fails, throws bad_cast
  ap = dynamic_cast<A*>(bp);     // fails: B is not a public base of D
  bp = dynamic_cast<B*>(ap);     // fails: D's B base is not public
  ap = dynamic_cast<A*>(&d);     // succeeds: ¶4 upcast
  // bp = dynamic_cast<B*>(&d);  // ill-formed: upcast to a private base
}

class E : public D, public B {};
class F : public E, public D {};

void h() {
  F  f;
  A* ap  = &f;                   // succeeds: A is a virtual base, only one in F
  D* dp  = dynamic_cast<D*>(ap); // fails, null pointer: F has two Ds
  // E* ep = (E*)ap;             // ill-formed: can't downcast from a virtual base
  E* ep1 = dynamic_cast<E*>(ap); // succeeds: F has only one E
  (void)dp; (void)ep1;
}

int main() { g(); h(); }
```

Three points can be read from it:

- The object does have a `B` subobject, but it comes through private inheritance, which neither step of paragraph 9 recognizes, so the conversion fails. An upcast to a private base, on the other hand, is an error at compile time and isn't deferred to run time.
- The offset of a virtual base class subobject relative to the whole object is unknown at compile time, so neither `static_cast` nor a C-style cast can downcast from a virtual base ([[expr.static.cast#10]]); `dynamic_cast` looks up the object layout at run time and can.
- `F` has two `D` subobjects; starting from the single shared `A`, there is no way to know which to choose, neither 9.1 nor 9.2 is satisfied, and the conversion fails.

When compiling this code, Clang 23 gives a direct base is inaccessible due to ambiguity warning for each of `E` and `F`, which is exactly the hint about duplicate subobjects.

## During construction and destruction

Note 1 after paragraph 10 points to [[class.cdtor#6]]: in a constructor or destructor (including functions they call directly or indirectly), if the operand refers to the object under construction or destruction, that object is treated as a most derived object whose type is the class of the current constructor or destructor.

```cpp run title="dyn-ctor.cpp" ok
struct V { virtual ~V() = default; };
struct D;
struct B : V { B(); bool saw_d = true; };
struct D : B {};

B::B() {
  V* v = this;
  saw_d = dynamic_cast<D*>(v) != nullptr;  // fails: at this point the object is treated as a B
}

int main() {
  D d;
  V* v = &d;
  bool after = dynamic_cast<D*>(v) != nullptr;  // after construction: succeeds
  return !d.saw_d && after ? 0 : 1;
}
```

This is the same reasoning as virtual calls during construction dispatching to the current class ([[class.cdtor#4]]): the derived part hasn't been constructed yet, and no mechanism may reach it. In implementations, while `B` is being constructed, the object's vtable pointer points to `B`'s vtable.

[[class.cdtor#6]] also says that if the operand refers to the object under construction and its static type is neither the current class nor one of its bases, the behavior is undefined.

## Constant evaluation

Since C++20 ([[P1327R1]]), `dynamic_cast` can appear in constant expressions. The constant evaluator knows the exact type of every object, so the check is exact:

```cpp run title="dyn-constexpr.cpp" ok
struct B { virtual ~B() = default; };
struct D : B {};
struct E : B {};

constexpr bool test() {
  D d;
  B* p = &d;
  return dynamic_cast<D*>(p) != nullptr
      && dynamic_cast<E*>(p) == nullptr;
}
static_assert(test());

int main() {}
```

There are two cases that are not core constant expressions ([[expr.const.core#2]]):

- ¶2.30 the dynamic type of the object referred to by the operand is not known at compile time, e.g. an object referred to by a function parameter;
- ¶2.31 a failed conversion would throw `std::bad_cast`, and no definition of that exception type is reachable (e.g. `<typeinfo>` wasn't included). C++26 allows throwing and catching exceptions during constant evaluation, so when the definition is reachable, a failed reference conversion can be caught at compile time.

## Implementation view

!!! impl "dynamic_cast in the Itanium C++ ABI"
    The Itanium C++ ABI used by GCC and Clang on Linux and macOS implements the cases like this:

    - Upcasts: the offset is computed at compile time, and the generated code is the same as `static_cast`; through a virtual base, the offset is read from the vtable. No RTTI needed.
    - Conversion to `void*`: the vtable has an offset-to-top slot recording the distance from the current subobject to the start of the most derived object; just add it. No RTTI needed either. Clang 23 still accepts `dynamic_cast<void*>` under `-fno-rtti`, but rejects other `dynamic_cast`s that need a runtime check.
    - Downcasts and cross-casts: call the runtime library function `__dynamic_cast`. It first finds the most derived object via offset-to-top, then walks the whole inheritance graph starting from the most derived object's `type_info`, looking for a public `C` subobject and checking uniqueness. The compiler also passes a statically computed hint to speed up common cases.
    - The walk compares `type_info`s. When type names are unique in the program, comparing pointers suffices; under some platform and shared-library configurations, the name strings have to be compared, which is more expensive.

!!! impl "Fast path for final classes"
    When the target class is `final`, the most derived object can only be of that class itself, so the check can be reduced to comparing the object's vtable pointer with the address of `C`'s vtable. Clang 23 compiling `dynamic_cast<D*>(b)` (with `D` `final`) with `--target=x86_64-linux-gnu -O2` generates exactly one pointer comparison; compiled for the default macOS target, it still calls `__dynamic_cast`. Whether this can be done depends on whether vtables are unique across the program, so it depends on the target platform and linking model.

A non-final `dynamic_cast` has to call into the runtime library and walk the inheritance graph, and is usually much more expensive than a virtual call. Performance-sensitive code often uses alternatives: put a virtual function returning a type tag in the base class and then `static_cast`; or use `std::variant` instead of an inheritance hierarchy. LLVM's own `isa<>` and `dyn_cast<>` are hand-written tags plus `static_cast`, and LLVM itself is compiled with `-fno-rtti`.

## History and evolution

!!! history
    - C++98: `dynamic_cast` was standardized together with RTTI.
    - C++11: the target type can be an rvalue reference, giving an xvalue.
    - C++20: usable in constant expressions ([[P1327R1]]).

## Common misconceptions

!!! pitfall "Using dynamic_cast to check whether a pointer is still valid"
    Applying `dynamic_cast` to a destroyed object is undefined behavior (¶7); it doesn't return a null pointer, it reads freed memory.

!!! pitfall "If the object contains that base class, the conversion always succeeds"
    Private or protected inheritance paths don't count in the runtime check, so the conversion fails; an upcast to such a base fails to compile outright.

!!! pitfall "Converting to the derived class in a base class constructor"
    In a base class's constructor or destructor, `dynamic_cast<Derived*>(this)` always gives a null pointer. This is behavior required by the rules, not a compiler problem.

!!! pitfall "dynamic_cast across shared libraries fails unexpectedly"
    When the same class has a separate `type_info` in each of two shared libraries (e.g. because symbol visibility is set to hidden), type comparison fails on some platforms and `dynamic_cast` returns a null pointer. The standard doesn't deal with shared libraries, but this is a common cause of unexpected `dynamic_cast` failures in practice.

## Questions

!!! question "Question 1"
    ```cpp
    struct L { virtual ~L(); };
    struct R { virtual ~R(); };
    struct X : L, R {};
    struct Y : X, R {};   // Y contains two Rs
    ```
    After `Y y; L* pl = static_cast<X*>(&y);`, what is the result of `dynamic_cast<R*>(pl)`?

<details markdown="1">
<summary>Answer</summary>

¶9.1 doesn't apply: the `L` subobject that `pl` points to is not part of any `R`; `L` and `R` have no inheritance relationship. ¶9.2 doesn't apply either: the most derived object `Y` has two `R` subobjects (one via `X`, one inherited directly), so `R` is an ambiguous base. The check fails and the result is a null pointer.

To get the `R` via `X`, first `dynamic_cast<X*>(pl)` (¶9.1 succeeds), then upcast implicitly to `R*`.
</details>

!!! question "Question 2"
    Why does `dynamic_cast<void*>(p)` require `*p` to be of polymorphic type, while `static_cast<void*>(p)` doesn't? When do their results differ?

<details markdown="1">
<summary>Answer</summary>

`dynamic_cast<void*>` looks for the start of the most derived object, which requires knowing at run time which larger object `*p` belongs to; only polymorphic objects carry that information, via the vtable. `static_cast<void*>(p)` only changes the pointer's type and doesn't care about any larger object.

Their values differ when `*p` is a base class subobject not at the start of some object, such as the second base class with multiple inheritance.
</details>

## Summary

!!! summary
    | Case | Wording | Needs polymorphism | Can fail |
    |---|---|---|---|
    | Same type | ¶3 | No | No |
    | Upcast | ¶4 | No | No; ill-formed at compile time if the base is inaccessible or ambiguous |
    | Conversion to `void*` | ¶8 | Yes | No |
    | Downcast | ¶9.1 | Yes | Yes |
    | Cross-cast | ¶9.2 | Yes | Yes |
    | Failure | ¶10 | | A pointer gives null, a reference throws `std::bad_cast` |
    | Operand doesn't point to a live object | ¶7 | | Undefined behavior |
