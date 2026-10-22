---
title: "The C++ object model: storage, objects, lifetime, pointer values"
summary: Looking at storage, objects, lifetime and pointer values in the abstract machine separately, and using that to decide whether there is an object in a piece of memory, whether the pointer in hand points to it, and when std::launder is needed.
tags: object model, lifetime, pointers, launder, topic
updated: 2026-10-19
---

!!! tldr
    - Storage, objects, lifetime and pointer values are four different things: having memory doesn't mean having an object, having an object doesn't mean it's alive, and having the same address doesn't mean a pointer points to it.
    - Objects come from only five sources; casts, writing a value, and `std::launder` don't create objects. Since C++20, operations such as `malloc` and `memcpy` implicitly create objects, which gives C-style code defined behavior.
    - A pointer value remembers which object it points to: a past-the-end pointer doesn't point to an adjacent object, pointer arithmetic can't leave its own array, and `reinterpret_cast` changes what a pointer points to only when the two objects are pointer-interconvertible.
    - `std::launder` doesn't create objects; it only turns a pointer with the right address that points to an old object into one that points to the new object. The easiest alternative is to keep the return value of placement new.

## The same address, two verdicts

<div class="compare" markdown="1">

```cpp run ok
#include <new>
int a() {
  alignas(int) unsigned char
    buf[sizeof(int)];
  int* p = new (buf) int(42);
  return *p;      // OK
}
```

```cpp run ub
#include <new>
int b() {
  alignas(int) unsigned char
    buf[sizeof(int)];
  new (buf) int(42);
  return *reinterpret_cast<int*>(buf);
  // UB: the pointer still points to buf[0]
}
```

</div>

Both functions put the same `int` at the same address, and Clang 23 at `-O2` compiles them to exactly the same code: return 42 directly. Yet the standard considers the left one valid and the right one undefined behavior.

The difference is what the pointer points to. On the left, `p` is the return value of placement new and points to the newly created `int`. On the right, the pointer is converted from `buf`, and by the rules still points to the array element `buf[0]`, so we are reading an `unsigned char` object through an lvalue of type `int`. Explaining this requires separating four layers of the C++ abstract machine:

| Layer | What it is | Specified in |
|---|---|---|
| Storage | Bytes, and the duration of a region of storage from acquisition to release | [[intro.memory]], [[basic.stc]] |
| Object | An entity that occupies a region of storage, with a type fixed at creation | [[intro.object]] |
| Lifetime | A run-time property of an object: from completion of initialization until destruction begins or the storage is reused | [[basic.life]] |
| Pointer value | Points to an object, past the end of an object, null, or invalid | [[basic.compound]] |

C programmers are used to seeing memory as one big byte array and pointers as indices. In C++ there is no automatic correspondence between these four layers; we'll go up through them one at a time.

## Storage

[[intro.memory]] describes memory as a sequence of contiguous bytes, each with a unique address. [[basic.stc]] specifies four storage durations (static, thread, automatic, dynamic), which determine when the **duration of the region of storage** begins and ends: it begins at program start or on entry to a block, and ends at program end, on leaving the block, or on deallocation.

Storage itself has no type. Memory from `malloc`, an `unsigned char` array, the space for a local variable on the stack: all are just places where objects can go. At the storage level there are only two questions: is the storage still there, and is its size and alignment sufficient ([[basic.align]]).

Whether a pointer is usable depends on the storage, not the object. This is expanded on in the section on pointer values below.

## Objects

### Where objects come from

[[intro.object#1]] lists all the ways an object can be created; there are five:

1. A definition, such as `int x;`;
2. A *new-expression*, including placement new;
3. An operation that implicitly creates objects (since C++20, see below);
4. Implicitly changing the active member of a union, such as `u.f = 1.0f;` ([[class.union#5]]);
5. Creating a temporary object ([[conv.rval]], [[class.temporary]]).

There is no other way. Casts don't create objects, writing a value into a piece of memory doesn't create an object (this differs from C; see below), and neither does `std::launder`.

An object's properties are determined at creation, and its type never changes. The only way to use the same storage as a different type is to create a new object there, which ends the lifetime of the old one.

### Subobjects and providing storage

There are three containment relations between objects, used when deciding whether addresses can be the same and whether `launder` is needed:

- **Subobject** ([[intro.object#2]]): members, base class subobjects, array elements. If a new object of the same type is created exactly over the storage of a subobject *e*, the enclosing object is alive, and *e* is not a potentially-overlapping subobject, the new object becomes a subobject of the enclosing object, called the [[g:corresponding-direct-subobjects|corresponding direct subobject]] of *e*. Types like `std::optional` rely on this to rebuild members in place.
- **Provides storage** ([[intro.object#3]]): when a complete object is created inside an `unsigned char[N]` or `std::byte[N]` array, the array provides storage for it, and the array's own lifetime doesn't end. `char` arrays are not included: placement new of an object in a `char` array reuses the storage of the array elements, and those `char` elements' lifetimes end.
- **Nested within** ([[intro.object#4]]): the transitive closure of the two relations above.

The standard's examples and edge cases are in [[intro.object]].

## Lifetime

**Lifetime** is a run-time property of objects and references ([[basic.life#2]]). The lifetime of an object of type `T` begins when two conditions are both met: storage with the proper size and alignment has been obtained, and its initialization is complete. If default-initialization does nothing, for example because a trivial default constructor was selected, it is called **vacuous initialization** and also counts as complete.

The lifetime ends when an object of non-class type is destroyed; when the destructor call of a class-type object starts; or when the storage is released or reused by an object that is not nested within it.

Putting storage, objects and lifetime together gives several easily confused states:

| State | Example | What you can do |
|---|---|---|
| Storage, no object yet | `operator new` has just returned and the constructor hasn't run (and nothing was implicitly created) | Use it as a `void*` |
| Object alive, value indeterminate | `*p` after `int* p = new int;` | Write; reading is UB ([[basic.indet]]) |
| Object alive, value erroneous | `x` after `int x;` (C++26) | Write; reading is erroneous behavior |
| Under construction or destruction | `*this` inside a constructor body | Subject to [[class.cdtor]] |
| Lifetime ended, storage still there | After `p->~T();` | Pointers and glvalues may only be used in limited ways ([[basic.life#7]], [[basic.life#8]]) |
| Storage released | After `delete p;` | The pointer is invalid in later evaluations ([[basic.compound#6]]) |

An indeterminate value and being outside the lifetime are two different things. In the former the object exists and only its value can't be read; in the latter the object is no longer there, and both reading and writing are UB (¶8.1 of [[basic.life#8]]).

When an object dies, pointers to it don't change. According to the footnote to [[basic.compound#3]], a pointer to an object that is not within its lifetime represents the first byte that the object will occupy or used to occupy. So after a new object is created in place, a rule is needed to say when old pointers automatically point to the new object; that is transparent replacement, described later.

## Implicit object creation {{c++20}}

```cpp run title="malloc-struct.cpp" ok
#include <cstdlib>
struct Pt { int x, y; };
int main() {
  Pt* p = static_cast<Pt*>(std::malloc(sizeof(Pt)));
  p->x = 1;       // C++17's literal rules: no object, UB; C++20: OK
  p->y = 2;
  int r = p->x + p->y;
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

In C++17 and earlier, `malloc` wasn't one of the five ways of creating objects; by the literal rules `p` points to no object, and `p->x = 1` is UB. [[P0593R6]] introduced **implicit object creation** as a defect fix ([[intro.object#13]]–[[intro.object#16]]):

!!! std
    That operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

An operation specified to implicitly create objects creates zero or more objects in its region of storage and starts their lifetimes, provided that doing so gives the program defined behavior. You can think of it as the abstract machine foreseeing, at the moment of `malloc`, how the program will use the memory later, and creating exactly the objects that make those uses valid.

- Only objects of **implicit-lifetime types** are created: scalars, implicit-lifetime classes, and arrays ([[basic.types.general#7]]). An implicit-lifetime class is an aggregate whose destructor is not user-provided, or a class with at least one trivial eligible constructor and a trivial, non-deleted destructor ([[class.prop#8]]). `std::string` is never implicitly created; non-trivial types can only be created by a *new-expression*.
- If no set of objects would give the program defined behavior, the behavior is undefined; if several sets would, which one is chosen is unspecified.
- Some operations also return a pointer to a suitable created object ([[intro.object#14]]), such as `malloc`, `operator new` and `memcpy`. An `unsigned char` array beginning its lifetime has no return value, and a pointer obtained from the array by decay still points to an array element. That is exactly the problem with the code on the right at the start.
- Implicit creation doesn't happen during constant evaluation ([[intro.object#16]]). The compile-time evaluator has to track every object precisely.

Operations that implicitly create objects:

| Operation | Source | Returns a pointer to a created object? |
|---|---|---|
| An `unsigned char[N]` or `std::byte[N]` beginning its lifetime | [[intro.object#16]] | No; the array provides storage for those objects |
| Calling `operator new`, `operator new[]` | [[intro.object#16]] | Yes |
| `malloc`, `calloc`, `realloc`, `aligned_alloc` | [[c.malloc#4]] | Yes |
| `memcpy`, `memmove` | [[cstring.syn#3]] | Yes |
| `std::bit_cast` | [[bit.cast]] | Creates nested objects in the result |
| `std::allocator<T>::allocate` | [[allocator.members]] | Creates a `T[n]` array without starting the elements' lifetimes |
| `std::start_lifetime_as<T>` {{c++23}} | [[obj.lifetime]] | Yes, and preserves the existing bytes |

## Pointer values

### A pointer value is not an address

[[basic.compound#3]] says every value of pointer type is exactly one of the following: a pointer to an object or function; a pointer past the end of an object; the null pointer value of that type; or an invalid pointer value. Pointers of the first two kinds represent an address, but the value itself is more than an address.

```cpp run title="past-end.cpp" ub
#include <cstdio>
int x = 1, y = 2;
int main() {
  int* p = &x + 1;              // past-the-end pointer of x: OK
  int* q = &y;
  if (p == q) {                 // unspecified result, may be equal
    *p = 10;                    // UB: p does not point to y
    std::printf("y = %d\n", y);
  }
}
```

!!! std
    A pointer past the end of an object is not considered to point to an unrelated object of the object's type, even if the unrelated object is located at that address.

A past-the-end pointer doesn't point to another object of the same type that happens to be at that address ([[basic.compound#3]] Note 2). So even if `p == q` holds, that doesn't mean `p` points to `y`, and a past-the-end pointer can't be dereferenced.

Clang 23 at `-O2` places `x` and `y` adjacently, and the program prints `y = 10`, not exploiting this UB. But a provenance-based alias analysis would be entirely entitled to conclude that `p` can't alias `y`, so a subsequent read of `y` could just use the old value 2.

### Pointer arithmetic can't leave its own array

[[expr.add#4]] confines pointer arithmetic to the range `[0, n]` of a single array object; an object that isn't an array element is treated as a one-element array, and going out of bounds is UB. [[expr.add#6]] also requires the pointer type to be similar to the array element type. Here is the standard's example from that clause:

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;      // OK: an int object may be accessed through an unsigned lvalue ([basic.lval]/11.2)
unsigned* q = p + 1;  // UB: p points to an element of an int array, and unsigned is not similar to int
```

Together the two rules form a rudimentary provenance rule: a pointer remembers which array it belongs to and can't reach another object by arithmetic.

### Pointer-interconvertibility and reachability

When does `reinterpret_cast` change what a pointer points to? It depends on whether the two objects are **pointer-interconvertible** ([[basic.compound#7]]): the same object; a union and one of its non-static data members; a standard-layout class object and its first non-static data member or any of its base class subobjects; and pairs obtained transitively from these. Two pointer-interconvertible objects have the same address, and `reinterpret_cast` can obtain a pointer to one from a pointer to the other ([[expr.static.cast#12]]). When they are not interconvertible, the conversion doesn't change the pointer value. An array and its first element have the same address but are not pointer-interconvertible.

[[basic.compound#8]] further defines the bytes **reachable through** a pointer: a pointer to an object *x* can reach the bytes occupied by any object *y* that is pointer-interconvertible with *x*; if *y* is an array element, it can reach the bytes of the whole immediately enclosing array. This concept is used only to constrain `std::launder` ([[ptr.launder#2]]): every byte reachable through the result must be reachable through the argument.

This restriction protects an important optimization:

```cpp
struct X { int a[2]; int b; };
void f(X& x, int* p);   // if p comes from &x.a[0], the compiler may assume *p and results of arithmetic on it can't touch x.b
```

If `std::launder(&x.a[0] + 2)` could get at `x.b`, the compiler could no longer assume pointers are confined to their own arrays. Reachability limits `launder`'s power to changing what it points to within the same set of reachable bytes.

### Pointers after storage ends

Under [[basic.compound#6]] in the current draft, whether a pointer is valid is a relation between a pointer value and an evaluation: a pointer to (or past) an object *O* is [[g:valid-in-the-context-of|valid in the context of]] an evaluation that occurs within the storage duration of *O*. In a context where it is invalid:

- Indirection through it (`*p`) is UB;
- Using it in a boolean conversion, unary `+`, addition or subtraction, or comparison has implementation-defined behavior;
- Copying and passing it are unrestricted.

This is new wording after C++23. C++23 said that when storage ends, all pointers to it become invalid pointer values, and even copying them was implementation-defined. The new wording means code such as comparing a possibly freed pointer in a lock-free data structure no longer falls into implementation-defined territory. See [[basic.compound]].

### Pointers obtained from integers and bytes

Pointers can also be recovered from integers or bytes:

- Integer to pointer ([[expr.reinterpret.cast#5]]): if the integer could have been obtained by converting some pointer values, the result is an unspecified one of those pointer values that would give the program defined behavior.
- Bytes to pointer ([[basic.types.trivial#1]]): `memcpy`ing bytes into a pointer object gives it a value representation, whose value is an unspecified member of the corresponding set that would give the program defined behavior. One value representation can correspond to several pointer values, which can point to objects in different regions of storage with disjoint durations.

Both follow the approach of implicit object creation: as long as some interpretation makes the program valid, that interpretation is used. This is close in spirit to the C committee's provenance model (PNVI-ae-udi), but the C++ wording has no explicit notion of exposure.

!!! impl
    Compilers don't yet implement the provenance semantics of integer-to-pointer conversion entirely consistently, and LLVM has had several miscompilation reports involving integer/pointer round trips. In practice, `reinterpret_cast<T*>(reinterpret_cast<std::uintptr_t>(p))` getting back the original pointer is safe; using integer arithmetic to cross objects and obtain a pointer to another object should not be relied on, even where the wording permits it.

## When `std::launder` is needed

!!! std
    *Returns*: A value of type T* that points to X.

The precondition of `std::launder(p)` is that at the address `p` represents there is an object *X* within its lifetime whose type is similar to `T`, and that every byte reachable through the result is reachable through `p`. It returns a pointer to *X* ([[ptr.launder]]). It doesn't create an object, doesn't change bytes, and doesn't generate machine instructions; it only turns a pointer value with the right address but the wrong target into a pointer value pointing to the object that actually exists there. For the optimizer it is also a barrier that stops the compiler from carrying over known facts about the old object, typically `const` members and the vtable pointer.

After a new object is created in place, old pointers automatically point to the new object if certain conditions hold. The condition is called **transparently replaceable** ([[basic.life#9]]): the two are complete objects of the same type (ignoring top-level cv) whose storage overlaps exactly, and the original object is not const; or the two are corresponding direct subobjects, and the enclosing complete object is not const (or the subobject is a `mutable` member). When this holds, by [[basic.life#10]], the original pointers, references and names automatically refer to the new object.

To decide whether the pointer `p` in hand points to the object *X* that currently exists at that address:

```text
Is p the return value of placement new / operator new / malloc / memcpy / start_lifetime_as?
  → Yes: use it directly.
Was X created in the storage of the object O that p originally pointed to?
  ├─ O is transparently replaceable by X ([basic.life]/9) → p automatically points to X; no launder needed.
  └─ No (O is a const complete object, different type, O is a base class subobject, ...) → std::launder(p) needed.
Was p converted from a pointer to another object (e.g. byte buffer → T*)?
  ├─ The two objects are pointer-interconvertible → the conversion already changed the target; not needed.
  └─ No → p still points to the original object (e.g. buf[0]); std::launder needed.
Otherwise → first confirm X really exists and its bytes are reachable through p; otherwise launder won't help.
```

Since C++20 the conditions for transparent replacement are quite permissive, and the cases that still need `launder` come down mainly to three:

1. After creating an object in a byte buffer, getting a pointer to it again from the buffer itself rather than from the return value of placement new. This is most common in implementations of `std::optional`, `std::variant` and small buffer optimizations.
2. The original object is a const complete object with dynamic storage duration. For const complete objects with static, thread or automatic storage duration, creating a new object in their storage is itself UB ([[basic.life#12]]), and `launder` doesn't help.
3. The original object is a base class subobject, or the new object has a different type.

```cpp run title="sbo.cpp" ok
#include <new>
#include <string>
#include <utility>

template <class T>
class Box {                                   // a minimal nullable box
  alignas(T) unsigned char buf_[sizeof(T)];   // buf_ provides storage for T
  bool full_ = false;
  T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }   // launder needed
public:
  template <class... A> void emplace(A&&... a) {
    reset();
    ::new (static_cast<void*>(buf_)) T(std::forward<A>(a)...);   // return value not kept
    full_ = true;
  }
  void reset() { if (full_) { ptr()->~T(); full_ = false; } }
  T& get() { return *ptr(); }
  ~Box() { reset(); }
};

int main() {
  Box<std::string> b;
  b.emplace("hello, object model");
  b.emplace(3, 'x');                          // destroys the old object, creates a new one in the same buf_
  return b.get() == "xxx" ? 0 : 1;
}
```

An `unsigned char` array is not pointer-interconvertible with `T`, so the value of `reinterpret_cast<T*>(buf_)` still points to `buf_[0]` ([[expr.static.cast#12]]). Without `launder`, it would access an `unsigned char` object through a glvalue of type `T`. Mainstream compilers generate the same code for both forms, but the version without `launder` only happens to work.

!!! tip "Keep the return value of placement new"
    The return value of `T* p = ::new (buf_) T(...);` is a pointer to the new object and needs no `launder`; the cost is storing one more pointer. Standard library implementations call `launder` on every access only to save those few bytes.

## Comparison with C's effective type model

C has no concept of creating objects; it constrains aliasing through **effective type** (C17 6.5p6):

| Question | C | C++ |
|---|---|---|
| What type is `malloc`ed memory | No declared type; it acquires an effective type on the first write through an lvalue of non-character type | `malloc` implicitly creates suitable objects on the spot |
| Using the same `malloc`ed memory as another type | Writing through the new type changes the effective type | A new object must be created, ending the old object's lifetime |
| Can a declared variable change type | No, its effective type is its declared type | Yes: by creating a new object in its storage (not const, and with the same type at destruction, [[basic.life#11]]) |
| Reading an inactive union member | Valid; the bytes are reinterpreted as the new type | UB, which must be diagnosed during constant evaluation |
| Pointer values | Address plus provenance (C's provenance model is still at the technical specification stage) | Points to an object; `launder`, transparent replacement and reachability all revolve around what it points to |
| Non-trivial types | Don't exist | Can only be created explicitly, e.g. by a *new-expression* |

Within the realm of trivial data plus `malloc` and `memcpy`, the two models reach the same conclusions, which was the design goal of P0593. They diverge on things C doesn't have: constructors, const objects, base class subobjects, `std::launder`. Carrying C intuitions over to C++ is usually fine in POD code, and goes wrong in generic containers, memory pools and serialization libraries.

## Puzzles

For each, is the marked line well-formed with defined behavior, or UB?

!!! question "Puzzle 1"
    ```cpp
    #include <cstdlib>
    struct P { int x, y; };
    int f() {
      P* p = static_cast<P*>(std::malloc(sizeof(P)));
      p->x = 1;
      return p->y;        // ?
    }
    ```

<details markdown="1">
<summary>Answer</summary>

UB, but not because there is no object. Since C++20, `malloc` implicitly creates `P` and its subobjects `x` and `y`, and `p->y` refers to an `int` that exists and is alive. The problem is its value: for storage with dynamic storage duration, the bytes initially have indeterminate values (¶1.1 of [[basic.indet#1]]), and reading an indeterminate value is UB (¶2). Automatic variables are different: `int y; return y;` is erroneous behavior in C++26, not UB.
</details>

!!! question "Puzzle 2"
    ```cpp
    #include <new>
    struct S { const int id; };
    int g() {
      S* s = new S{1};
      s->~S();
      new (s) S{2};
      int r = s->id;     // ?
      delete s;
      return r;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

OK since C++20, with `r == 2`. `*s` is a non-const complete object with dynamic storage duration, and the new object has the same type and exactly covers the original storage, so it is transparently replaceable (¶9.1 of [[basic.life#9]]), and `s` automatically points to the new object (¶10). In C++17's wording, a const member or reference member prevented transparent replacement, and `std::launder` was needed here; C++20 removed that condition.

If it were written `const S* s = new const S{1};`, the original object would be a const complete object, item 9.1.1 would not hold, and `std::launder(s)->id` would be needed; this is exactly the standard's example in [[ptr.launder]]. If `s` pointed to a const local variable with automatic storage duration, creating a new object in its storage would itself be UB ([[basic.life#12]]).
</details>

!!! question "Puzzle 3"
    ```cpp
    union U { int i; float f; };
    int k() {
      U u{.i = 1};
      int* p = &u.i;
      u.f = 2.0f;
      return *p;          // ?
    }
    ```

<details markdown="1">
<summary>Answer</summary>

UB. `u.f = 2.0f` is a built-in assignment to a union member, which by [[class.union#5]] implicitly creates `f` and makes it the active member; the storage of `i` is reused and its lifetime ends (¶2.5 of [[basic.life#2]]). `p` still points to the dead `u.i`, and `*p` reads an object that is not within its lifetime, violating ¶8.1 of [[basic.life#8]].
</details>

!!! question "Puzzle 4"
    ```cpp
    struct H { int tag; double d; };
    int m() {
      H h{1, 2.0};
      int* pt = reinterpret_cast<int*>(&h);
      *pt = 5;           // ?
      return h.tag;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

OK, returns 5. `H` is a standard-layout class, so `h` is pointer-interconvertible with its first non-static data member `h.tag` (¶7.3 of [[basic.compound#7]]), and the result of `reinterpret_cast` points to `h.tag` ([[expr.static.cast#12]]). The C idiom of treating a struct's first member as a header rests on this in C++. If `H` weren't standard-layout (for example, if it had virtual functions), the pointer value would be unchanged and still point to `h`, and `*pt = 5` would be UB.
</details>

!!! question "Puzzle 5"
    ```cpp
    #include <new>
    int n() {
      int arr[4] = {1, 2, 3, 4};
      auto pa = reinterpret_cast<int(*)[4]>(&arr[0]);
      auto pb = std::launder(pa);
      return (*pb)[1];    // ?   what about (*pa)[1]?
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`(*pb)[1]` is OK, `(*pa)[1]` is UB.

An array is not pointer-interconvertible with its first element ([[basic.compound#7]] Note 7), so `pa` still points to the `int` `arr[0]`, only with type `int(*)[4]`. `*pa` is an `int[4]` lvalue that refers to an `int` object, and the following array-to-pointer conversion has no array object to work from.

Both preconditions of `std::launder(pa)` hold: at the address there is a live object `arr` of type `int[4]`; the bytes reachable through `pa` are all the bytes of `arr`, the immediately enclosing array of `arr[0]` ([[basic.compound#8]]), which covers the bytes reachable through the result. So `pb` points to `arr`. This is another use of `launder`: changing the target where pointers aren't interconvertible.
</details>

!!! question "Puzzle 6"
    ```cpp
    #include <new>
    struct X { int a[2]; int b; };
    int q(X& x) {
      int* p = &x.a[0] + 2;           // past-the-end pointer of a; assuming no padding, its address equals &x.b
      return *std::launder(p);        // ?
    }
    ```

<details markdown="1">
<summary>Answer</summary>

UB. `p` is a past-the-end pointer and doesn't point to any object; reachability is defined only for pointers to objects, so no bytes are reachable through `p` ([[basic.compound#8]]). `std::launder` requires every byte reachable through the result (the 4 bytes of `x.b`) to be reachable through the argument, so its precondition isn't met. This is exactly the optimization reachability is there to protect: pointers derived from `x.a` can't touch `x.b`. To get a pointer to `x.b`, write `&x.b`, or start from a pointer to `x`.
</details>

!!! question "Puzzle 7"
    ```cpp
    #include <cstdint>
    int x = 1, y = 2;
    int r() {
      auto n = reinterpret_cast<std::uintptr_t>(&x);
      int* p = reinterpret_cast<int*>(n + sizeof(int));
      if (p == &y) { *p = 10; return y; }    // ?
      return 0;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Under the current wording, if the `if` is entered, the behavior is defined and it returns 10. This contrasts with the earlier `&x + 1` example.

By [[expr.reinterpret.cast#5]], the integer value `n + sizeof(int)` can be obtained by converting pointer values (both `&x + 1` and `&y` convert to it), and the result is an unspecified one of those pointer values that would give the program defined behavior. Choosing the pointer to `y` makes `*p = 10` valid, so the abstract machine chooses it. What pointer arithmetic can't do (a past-the-end pointer never points to `y`), an integer round trip can.

Don't write this in practice. The provenance semantics of integer-to-pointer conversion is exactly where miscompilation reports cluster.
</details>

## Summary

| Question | Which layer | Key clauses |
|---|---|---|
| Is the memory still there | Storage | [[basic.stc]], [[basic.compound#6]] |
| Is there an object there, of what type | Object | [[intro.object#1]], [[intro.object#13]] |
| Is the object alive | Lifetime | [[basic.life#2]], [[basic.life#7]], [[basic.life#8]] |
| Can the value be read | Value | [[basic.indet]] |
| Does my pointer point to it | Pointer value | [[basic.compound#3]], [[basic.compound#7]], [[expr.static.cast#12]] |
| Can it be accessed through this type | Access | [[basic.lval#11]], see [[topics/type-punning]] |
| Will old pointers automatically point to the new object | Transparent replacement | [[basic.life#9]], [[basic.life#10]] |
| What if they won't | `std::launder` | [[ptr.launder]] |
