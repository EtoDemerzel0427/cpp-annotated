---
title: Object lifetime
summary: "An object's lifetime begins when its initialization completes and ends when destruction starts or its storage is reused; pointers and references outside the lifetime can be used only in limited ways; whether old names still work after a new object replaces the old one in place (transparent replaceability, std::launder); and two extra restrictions on scope exit and const objects."
updated: 2026-10-19
---

!!! tldr
    - An object's lifetime begins when its storage is ready and its initialization is complete; a class object's lifetime ends when its destructor starts, a non-class object's when it is destroyed; it also ends when the storage is released or reused by another object.
    - Outside the lifetime, a pointer to the object can only be used as a `void*`; member access, `delete`, conversion to a virtual base, and `dynamic_cast` are UB. The same goes for references and names: the object's value cannot be read or written.
    - After a new object of the same type is created in place, whether old pointers, references and names automatically refer to the new object depends on whether the old one is **transparently replaceable**: for complete objects this requires non-`const`, exact overlay, and the same type.
    - When it is not transparently replaceable, use the return value of placement new, or call `std::launder` on the old address.
    - For local, static and thread objects with non-trivial destructors, an object of the original type must be in place when the scope ends; no new object may be created in the storage of such an object that is `const`.

## Where lifetime begins (¶2)

```cpp run title="lifetime-begin.cpp" ok
#include <string>

void f() {
    int x;                      // lifetime begins here (the value is erroneous, see [basic.indet])
    std::string s("abc");       // begins when the constructor returns
    struct P { int a, b; } p;   // trivial default construction: begins here
    (void)x; (void)p;
}

int main() { f(); }
```

An object's **lifetime** is a run-time property. Only within its lifetime can the object be read and written normally according to its type and have its member functions called. Per ¶2, the lifetime of an object of type `T` begins when both of these are done:

- ¶2.1 storage with the proper alignment and size for type `T` is obtained;
- ¶2.2 its initialization (if any) is complete.

A declaration like `int x;` does nothing and still counts as complete initialization. The standard calls this **vacuous initialization**: the variable is default-initialized, no other initialization is performed, and, if it is of class type (or an array thereof), the default initialization selects a trivial constructor.

For class types, initialization is complete when the constructor finishes. While the constructor body runs, the object is in its period of construction: not entirely unusable, but not yet within its lifetime either. The rules for this period are in [[class.cdtor]]; for example, virtual functions dispatch to the class being constructed.

### Union members

If the object is a union member or a subobject thereof, its lifetime begins only if that member is the initialized member of the union. There are a few other routes: assigning to a member changes the active member ([[class.union]]), trivially copying a union copies its active member ([[class.copy.ctor]], [[class.copy.assign]]), and `std::start_lifetime_as` can also begin a lifetime ([[obj.lifetime]]).

```cpp run title="union-lifetime.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};     // u.i's lifetime begins; u.f is not within its lifetime
    u.f = 2.0f;      // the assignment changes the active member: u.f begins, u.i ends
    return u.f == 2.0f ? 0 : 1;   // OK
    // reading u.i now would be UB: u.i is not within its lifetime
}
```

Another exception is in [[allocator.members]]: `std::allocator<T>::allocate` creates an array object but does not begin the lifetimes of its elements; see the `vector`-style storage example later.

## Where lifetime ends (¶2)

The lifetime of an object *o* of type `T` ends when any of the following happens:

- ¶2.3 if `T` is a non-class type, the object is destroyed, for example by `std::destroy_at(&x)`, a pseudo-destructor call `p->~int()`, or the end of its storage duration;
- ¶2.4 if `T` is a class type, the destructor call starts;
- ¶2.5 the storage the object occupies is released, or is reused by an object that is not nested within *o* ([[intro.object]]).

¶2.4 says the destructor starts, not finishes. While the destructor body runs, the object is no longer within its lifetime but in its period of destruction, also governed by [[class.cdtor]].

The "not nested within *o*" in ¶2.5 is an opening left for `unsigned char` buffers. When an object is created by placement new in an `unsigned char` array, the array **provides storage** for the new object ([[intro.object#3]]); the new object is nested within the array, and the array's lifetime does not end because of it.

### In a new-expression, reuse happens before initialization

The last sentence of ¶2 specifies that when a *new-expression* is evaluated, the storage is considered reused as soon as the allocation function returns, which is before the *new-initializer* (the initializer in parentheses or braces) is evaluated. So the initializer cannot read the old object:

<div class="compare" markdown="1">

```cpp run ub
#include <new>
struct S { int m; };

int main() {
  S x{1};
  ::new (&x) S(x.m);  // UB
  return x.m;
}
```

```cpp run ok
#include <new>
struct S { int m; };

int main() {
  S x{1};
  int v = x.m;        // read it first
  ::new (&x) S(v);    // OK
  return x.m;
}
```

</div>

On the left, when `x.m` is evaluated, the storage of `x` is already considered reused and the old `x`'s lifetime has ended. This also explains why the assignment idiom `this->~T(); new (this) T(other);` is wrong when `other` is `*this`: after destruction, `other` is no longer within its lifetime.

## What can be done outside the lifetime (¶5, ¶7, ¶8)

¶5 says that properties ascribed to objects or references anywhere in the standard apply only during their lifetime. What can be done outside the lifetime must be permitted separately by ¶7, ¶8 and [[class.cdtor]].

"Outside the lifetime" here means two periods: after the storage is allocated but before the lifetime begins, and after the lifetime ends but before the storage is reused or released. Objects under construction or destruction are covered by [[class.cdtor]].

### Pointers (¶7)

¶7 allows limited use of a pointer to such storage. Using it as a `void*` is well-defined, and it can be dereferenced, but the resulting lvalue can only be used in the limited ways of ¶8. The following uses are UB:

| Item | Use | Why not |
|---|---|---|
| ¶7.1 | as the operand of a *delete-expression* | `delete` calls the destructor |
| ¶7.2 | accessing a non-static data member or calling a non-static member function | requires the object to exist |
| ¶7.3 | conversion to a pointer to a virtual base class (or a base of one) | the virtual base offset is looked up through the object's vptr |
| ¶7.4 | as the operand of `dynamic_cast` | reads the vptr to get the dynamic type |

Uses not on the list are allowed: copying and comparing the pointer, converting it to `void*`, converting it to a pointer to a non-virtual base (the offset is known at compile time, so the object need not be read).

The following is adapted from Example 2 in the standard:

```cpp run title="mutate.cpp" ub
#include <cstdlib>
#include <new>

struct B {
    virtual void f() {}
    void mutate();
    virtual ~B() {}
};
struct D1 : B { void f() override {} };
struct D2 : B { void f() override {} };

void B::mutate() {
    ::new (this) D2;   // reuses the storage, ending the lifetime of *this
    f();               // UB: ¶7.2, this->f()
    void* p = this;    // OK: used as a void*
    (void)p;
}

int main() {
    void* p = std::malloc(sizeof(D1) + sizeof(D2));
    B* pb = ::new (p) D1;
    pb->mutate();
    void* q = pb;      // OK
    (void)q;
    pb->f();           // UB: the lifetime of *pb has ended
    std::free(p);
}
```

Why can't `pb->f()` reach `D2::f`? The compiler knows `pb` points to a `D1` and may turn `pb->f()` into a direct call to `D1::f`. The `mutate()` call in between does not affect this inference: it cannot quietly turn the `D1` into a `D2`, because that would end the object's lifetime, and accessing through `pb` afterward is UB. To use the new object, use the return value of placement new: `B* pb2 = ::new (p) D2; pb2->f();`.

### References and names (¶8)

¶8 is the glvalue version of the same rule (a glvalue is an expression that refers to an object, such as a variable name or `*p`). During the same periods, properties that do not depend on the object's value may be used, such as taking the address or binding a reference of the same type. The following uses are UB:

| Item | Use |
|---|---|
| ¶8.1 | accessing the object, i.e. reading or writing its value |
| ¶8.2 | calling a non-static member function |
| ¶8.3 | binding to a reference to a virtual base class |
| ¶8.4 | as the operand of `dynamic_cast` or `typeid` |

```cpp run title="glvalue-outside.cpp" ub
#include <memory>

int main() {
    int x = 1;
    std::destroy_at(&x);   // ends the lifetime of x
    int* p = &x;           // OK: taking the address does not depend on the value
    int& r = x;            // OK: binds a reference of the same type
    (void)p;
    return r;              // UB: ¶8.1, reads an object outside its lifetime
}
```

### Multiple threads (¶1)

¶1 specifies that "before" and "after" in [basic.life] are to be understood in terms of the [[g:happens-before]] relation, not sequential order in a single thread. So note 5 points out that if one thread refers to an object that another thread is constructing, without proper synchronization, the behavior is undefined. Without synchronization there is no "after construction is complete". This is exactly where the broken double-checked locking idiom goes wrong.

## Replacing an object in place: transparent replaceability (¶9–¶10)

After the old object's lifetime ends, a new object is created at the same place. Can pointers, references and names that referred to the old object be used directly for the new one?

```cpp run title="transparent-replace.cpp" ok
#include <new>

struct C {
    int i;
    void f() {}
    C(int i) : i(i) {}
    C(const C&) = default;
    const C& operator=(const C& other);
};

const C& C::operator=(const C& other) {
    if (this != &other) {
        this->~C();              // the lifetime of *this ends
        ::new (this) C(other);   // a new object of the same type is created at the same place
        f();                     // OK: this points to the new object
    }
    return *this;
}

int main() {
    C c1{1}, c2{2};
    c1 = c2;                     // OK
    c1.f();                      // OK: the name c1 refers to the new object
    return c1.i == 2 ? 0 : 1;
}
```

¶10 answers: if the old object *o1* is **transparently replaceable** by the new object *o2*, then pointers to *o1*, references to *o1* and the name of *o1* automatically refer to *o2* and, once *o2*'s lifetime has begun, can be used to manipulate it. The example above is such a case.

¶9 gives the definition. *o1* is transparently replaceable by *o2* in either case one or case two.

Case one (¶9.1): both are complete objects (not subobjects of any object), and

- ¶9.1.1 *o1* is not `const`;
- ¶9.1.2 the storage *o2* occupies exactly overlays the storage *o1* occupied;
- ¶9.1.3 they are of the same type, ignoring top-level cv-qualifiers.

Case two (¶9.2): they are **corresponding direct subobjects**, and either the complete object of *o1* is not `const` (¶9.2.1), or *o1* is a `mutable` member subobject or a subobject thereof (¶9.2.2).

Corresponding direct subobjects are defined in [[intro.object#2]]: when a new object is created in the storage of some subobject *e*, if the object containing *e* is within its lifetime, the new object exactly overlays *e*, *e* is not a potentially-overlapping subobject, and the types are the same, then the new object becomes a subobject of the same enclosing object and corresponds to *e*. Potentially-overlapping subobjects are base class subobjects and members marked `[[no_unique_address]]`; their storage may be shared with other subobjects, so they are excluded.

### Each condition protects an optimization

| Condition | Optimization it protects |
|---|---|
| the old object is not a `const` complete object | the compiler may assume a `const` object's value does not change, and propagate constants |
| exact overlay | pointer arithmetic and subobject offsets stay consistent between old and new objects |
| same type | the dynamic type (vptr) does not change, allowing devirtualization |
| not a base class subobject | a base class subobject's dynamic type is the derived class, and replacing it with a complete object of the base type would change it; its storage may also be shared with other members |

### `const` and reference members no longer prevent replacement {{c++20}}

C++17's ¶9 had one more requirement: the class type must not contain non-static data members of `const`-qualified or reference type. The quite natural code below was therefore UB and required `std::launder`. C++20 removed that restriction, and it is now well-formed:

```cpp run title="const-member.cpp" ok
#include <new>

struct X { const int n; int& r; };

int main() {
    int a = 1, b = 2;
    X x{1, a};
    x.~X();
    ::new (&x) X{2, b};   // C++17: x can no longer be used to access the new object
    return x.n + x.r;     // OK since C++20
}
```

One motivation for the removal was the standard library: when the elements of `std::optional<X>` or `std::vector<X>` contain `const` members, an implementation strictly following C++17 would have had to `launder` on every access, which was both clumsy and an obstacle to optimization.

What remains is that the complete object itself cannot be `const`. Here is the example from [[ptr.launder]]:

```cpp run title="const-complete.cpp" ok
#include <new>

struct X { int n; };

int main() {
    const X* p = new const X{3};
    const int a = p->n;
    ::new (const_cast<X*>(p)) const X{5};   // p does not point to the new object: the original is a const complete object
    // const int b = p->n;                  // UB: p still points to the old object, whose lifetime has ended
    const int c = std::launder(p)->n;       // OK
    delete std::launder(p);
    return a + c == 8 ? 0 : 1;
}
```

This is a `const` object of dynamic storage duration, so ¶12 does not apply. For a local or static `const` complete object, even creating the new object is UB; see below.

### When transparent replacement is not possible: `std::launder`

Note 6 in ¶10 says that when the conditions are not met, a pointer to the new object can be obtained by calling `std::launder` ([[ptr.launder]]) on a pointer that represents the address of the storage. `launder` itself has a precondition: there must be an object of a similar type, within its lifetime, at that address.

There are three typical cases needing `launder`: the original object is a `const` complete object (the example above); the pointer you hold originally pointed to an object of another type, such as an `unsigned char` buffer; or the replaced object is a base class subobject. Here is a minimal `optional`:

```cpp run title="optional-like.cpp" ok
#include <new>
#include <string>
#include <utility>

template<class T>
class Opt {
    alignas(T) unsigned char buf_[sizeof(T)];   // buf_ provides storage for T
    bool has_ = false;

    // without launder, the result of reinterpret_cast still points to buf_[0], and access is UB
    T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }

public:
    Opt() = default;
    ~Opt() { reset(); }
    template<class... A>
    T& emplace(A&&... a) {
        reset();
        T* p = ::new (buf_) T(std::forward<A>(a)...);
        has_ = true;
        return *p;           // the return value of placement new already points to the new object
    }
    void reset() { if (has_) { ptr()->~T(); has_ = false; } }
    T& operator*() { return *ptr(); }
};

int main() {
    Opt<std::string> o;
    o.emplace("hello");
    o.emplace("world");      // destroys the old string first, then constructs a new one in the same buf_
    return (*o).size() == 5 ? 0 : 1;
}
```

Another approach is to store the return value of placement new in a member `T* p_` and always access through it, at the cost of storing an extra pointer. Standard library implementations usually use a union member `union { T val_; };` as the storage: a new object constructed in the place of `val_` corresponds to `val_` as a direct subobject, is transparently replaceable, and access through the member name needs no `launder`.

### `vector`-style storage

```cpp run title="vector-like.cpp" ok
#include <memory>
#include <string>

int main() {
    std::allocator<std::string> a;
    std::string* p = a.allocate(3);   // creates a string[3] array object; the elements' lifetimes have not begun
    for (int i = 0; i < 3; ++i)
        std::construct_at(p + i, 3, char('a' + i));   // p + i is valid: p points to an array element
    std::string s = p[0] + p[2];      // OK: the elements are within their lifetimes
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return s == "aaaccc" ? 0 : 1;
}
```

Pointer arithmetic is defined only within an array object. If there were no array object in the storage returned by `allocate`, `p + i` would be UB, and `std::vector` could not be implemented in standard C++. [[P0593R6]] fixed this: [[allocator.members]] specifies that `allocate` creates a `T[n]` array object but does not begin the lifetimes of its elements; each element's lifetime begins after `construct_at`.

## Ending a lifetime without calling the destructor (¶6)

¶6 allows a program to end the lifetime of a class object by reusing or releasing its storage instead of calling its destructor. In that case the destructor is not implicitly called. Note 4 reminds us that the correctness of a program often depends on the destructor being called, for example to release resources; but skipping destruction is not UB in itself.

```cpp run title="skip-dtor.cpp" ok
#include <new>
#include <string>

int main() {
    alignas(std::string) unsigned char buf[sizeof(std::string)];
    auto* s = ::new (buf) std::string(100, 'x');   // allocates 100 bytes on the heap
    ::new (buf) int(0);   // reuses the storage: *s's lifetime ends, its destructor is not called
    (void)s;              // a memory leak, but not UB
}
```

Running it in our tests with AddressSanitizer and leak detection enabled (`ASAN_OPTIONS=detect_leaks=1`) reports this leak, but no UB.

## On scope exit, put the original type back (¶11)

The compiler unconditionally inserts a destructor call at the end of the scope; it does not know you swapped objects in between. So ¶11 specifies: if a program ends the lifetime of an object of type `T` with static, thread or automatic storage duration, and `T` has a non-trivial destructor, then an object of the original type must occupy that same storage location when the implicit destructor call takes place; otherwise the behavior is undefined. The same applies when the block is exited by an exception.

<div class="compare" markdown="1">

```cpp run ub
#include <new>
class T {};
struct B { ~B() {} };

void h() {
  B b;
  ::new (&b) T;  // ends b's lifetime
}  // UB: there is no B object here now

int main() { h(); }
```

```cpp run ok
#include <new>
struct T {};
struct B { ~B() {} };

void h() {
  B b;
  b.~B();
  T* t = ::new (&b) T;
  t->~T();
  ::new (&b) B;  // put a B back
}  // OK

int main() { h(); }
```

</div>

The version on the right requires that constructing `B` does not throw. If `::new (&b) B` throws, there is no `B` there when the scope is exited, which is also UB.

## The storage of `const` objects cannot be reused (¶12)

Creating a new object in the storage that a `const` complete object with static, thread or automatic storage duration occupies, or in the storage it occupied after its lifetime ended, is UB.

```cpp run title="const-static.cpp" ub
#include <new>

struct B { B() {} ~B() {} };

const B b;

void h() {
    b.~B();
    ::new (const_cast<B*>(&b)) const B;   // UB: ¶12
}

int main() { h(); }
```

Such objects may be placed in read-only memory (the `.rodata` section), where a write triggers a hardware exception; even if not, the compiler may already have propagated their value to every use. `const` objects of dynamic storage duration obtained with `new const X` are not subject to this rule.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶3 The lifetime of a reference begins when its initialization is complete, and it ends as if it were a scalar object requiring storage. A reference has no destructor; it ends when its storage duration ends or when the storage of the object containing it is reused.

¶4 is a note pointing to the description of the lifetimes of base and member subobjects in [[class.base.init]].

</details>

## Implementation view

!!! impl "How compilers exploit these rules"
    - Devirtualization: for `B* p = new D; p->f();`, the compiler knows the dynamic type of `*p` is `D` and can call `D::f` directly. Clang's `-fstrict-vtable-pointers` more aggressively assumes the vptr does not change during an object's lifetime, and treats `std::launder` as a barrier for such assumptions.
    - `const` propagation: the compiler assumes a `const` complete object's value does not change during its lifetime, so it can be loaded into a register early or folded into a constant. This is what ¶9.1.1 and ¶12 protect.
    - On GCC and Clang, `std::launder` is implemented as `__builtin_launder`, which generates no instructions; it only makes the optimizer drop its old assumptions about the object this pointer points to.
    - Compilers generate destructor calls directly at scope exits and in the landing pads of exception paths, which is where ¶11 comes from.

## History

!!! history
    - C++98 already had the concept of lifetime, lists like those in ¶7 and ¶8, and an early form of transparent replacement. The conditions then also included that the class contain no `const` or reference members.
    - C++17: [[P0137R1]] introduced `std::launder` along with the rewrite of the object model, giving a basis for obtaining a pointer to the new object when transparent replacement does not apply.
    - C++20: removed the restriction that the class must not contain `const` or reference members. The end-of-lifetime condition changed from "destructor starts, for class types with non-trivial destructors" to "destructor starts, for all class types" ([[CWG2256]]); pseudo-destructor calls also end the lifetime of non-class objects. [[P0593R6]] introduced implicit object creation and specified that `std::allocator::allocate` creates an array object.
    - New wording after C++23: transparent replacement of subobjects is phrased in terms of corresponding direct subobjects, explicitly excluding potentially-overlapping subobjects; ¶2 makes clear that a *new-expression* reuses the storage before the initializer is evaluated (Example 1).

## Common misconceptions

!!! pitfall "After placement new, old pointers always work"
    Only when the replacement is transparent. Common counterexamples: the replaced object is a base class subobject, the old and new types differ, or the original is a `const` complete object. When unsure, use the return value of placement new.

!!! pitfall "`std::launder` solves everything"
    `launder` only gives you a pointer to an object that already exists and is within its lifetime. If there is no object of that type at the address at all, for example using memory from `malloc` directly as a `std::string` without placement new, the precondition fails and the call itself is UB.

!!! pitfall "Reading members after destruction for debug output"
    `obj.~T(); log(obj.x);` is UB (¶8.1), even if the destructor does nothing. Since C++20, explicitly calling a trivial destructor ends the lifetime too.

## Questions

!!! question "Question 1"
    Does the program below have UB?

    ```cpp
    struct Base { virtual int id() { return 1; } virtual ~Base() = default; };
    struct Der : Base { int id() override { return 2; } };
    int main() {
        Der d;
        Base* pb = &d;
        pb->~Base();
        ::new (pb) Base;
        int r = pb->id();
        ::new (&d) Der;
        return r;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. `pb->~Base()` is a virtual destructor call that actually runs `Der::~Der()`, ending the lifetime of `d`. `::new (pb) Base` creates a complete `Base` object in this storage; here `pb` is used only as an address, which is fine.

But the old object is a base class subobject of `Der`: it is not a complete object, so ¶9.1 does not apply; a base class subobject is potentially overlapping, and the lifetime of `d` has also ended, so the new `Base` does not become a corresponding direct subobject, and ¶9.2 does not apply either. The replacement is not transparent, and `pb->id()` is UB under ¶7.2. Use the return value of placement new, or write `std::launder(pb)->id()`. The program puts a `Der` back at the end, so ¶11 is satisfied on scope exit.
</details>

!!! question "Question 2"
    What about `struct S { const int c; }; S s{1}; s.~S(); new (&s) S{2}; int v = s.c;` in C++17 and in C++20? And if it is changed to `const S s{1};` (automatic storage duration)?

<details markdown="1">
<summary>Answer</summary>

In C++17, `S` contains a `const` member, so it cannot be transparently replaced; `s.c` is UB and you must write `std::launder(&s)->c`. Since C++20, `s` is not a `const` complete object, the types are the same and the overlay is exact, so it is transparently replaceable and there is no problem.

With `const S s{1};`, creating a new object in the storage of a `const` complete object with automatic storage duration is UB outright under ¶12, and `launder` cannot fix it.
</details>

!!! question "Question 3"
    Why does ¶7 allow converting a `D*` outside its lifetime to a pointer to a non-virtual base, but forbid converting it to a pointer to a virtual base?

<details markdown="1">
<summary>Answer</summary>

The offset of a non-virtual base class subobject relative to the derived object is a compile-time constant; the conversion just adds a fixed value to the address and needs no read of the object. The offset of a virtual base class subobject depends on the most derived type and is usually looked up in the vtable through the object's vptr (the vbase offset in the Itanium ABI), which requires reading the object. When the object is not within its lifetime, the vptr may not be set yet, or may already have been rewritten during destruction.
</details>

## Summary

| Situation | Rule |
|---|---|
| Lifetime begins | storage ready and initialization complete (including vacuous initialization); a union member must become the active member |
| Lifetime ends | non-class: destroyed; class: destructor starts; or the storage is released or reused by a non-nested object |
| *new-expression* | the storage counts as reused after the allocation function returns, before the initializer is evaluated |
| Pointers outside the lifetime | usable as `void*`; `delete`, member access, conversion to a virtual base, and `dynamic_cast` are UB |
| Glvalues outside the lifetime | value-independent properties are usable; reading or writing, calling member functions, binding virtual base references, `dynamic_cast` and `typeid` are UB |
| Transparent replacement | complete objects: non-`const`, exact overlay, same type; subobjects: corresponding direct subobjects, with a non-`const` complete object or a `mutable` member |
| When not transparently replaceable | use the return value of placement new, or `std::launder` |
| Scope exit | static, thread and automatic objects with non-trivial destructors must have an object of the original type in place |
| `const` objects | no new object may be created in the storage of a `const` complete object with static, thread or automatic storage duration |
