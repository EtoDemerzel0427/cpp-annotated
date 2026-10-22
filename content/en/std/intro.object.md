---
title: Object model
summary: "Which constructs create objects; subobjects, complete objects and most derived objects; how byte arrays provide storage for other objects; when object sizes and addresses may overlap; and how operations like malloc and memcpy implicitly create objects."
updated: 2026-10-19
---

!!! tldr
    - In C++, having bytes does not mean having an object. Objects arise only in five ways: definitions, `new`, operations that implicitly create objects, changing the active member of a union, and creating temporary objects. `reinterpret_cast` is not one of them.
    - Only arrays of `unsigned char` and `std::byte` can provide storage for objects created in them without ending the array's own lifetime; `char` arrays cannot.
    - Two objects with overlapping lifetimes generally have different addresses. The exceptions are one nested within the other, zero-size subobjects, and mergeable objects such as string literals. Two subobjects of the same type never share an address.
    - `malloc`, `memcpy`, `operator new` and the start of a byte array's lifetime implicitly create objects of implicit-lifetime types as needed, giving C-style code defined behavior since C++20.
    - To get a pointer to an object implicitly created in a byte array, you need `std::launder` or C++23's `std::start_lifetime_as`; `reinterpret_cast` alone is not enough.

## Where objects come from (¶1)

Many programmers coming from C carry this model: memory holds some bytes, and whatever pointer type you look at them through, that is the type of the object. C++'s model is different. An object is an entity created by particular constructs, with a definite type, storage and lifetime; bytes are merely the medium carrying objects, and a pointer points to an object, not just to an address.

!!! std
    An *object* is created by a definition, by a *new-expression*, by an operation that implicitly creates objects (see below), when implicitly changing the active member of a union, or when a temporary object is created.

¶1 This is a closed list:

```cpp run title="creation.cpp" ok
#include <new>
#include <cstdlib>

union U { int i; float f; };
struct P { int x, y; };

int g;                                   // 1. definition

int main() {
    int* p = new int(42);                // 2. new-expression
    delete p;

    P* q = static_cast<P*>(std::malloc(sizeof(P)));   // 3. malloc implicitly creates a P (see ¶13 below)
    q->x = 1;
    std::free(q);

    U u{};                               // u.i is the active member
    u.f = 1.0f;                          // 4. the assignment changes the active member, creating a float object

    int n = P{1, 2}.x;                   // 5. P{1, 2} is materialized as a temporary object
    (void)n;
}
```

| Way | Example | Details |
|---|---|---|
| definition | `int x;`, `static S s;` | [[basic.def]] |
| new-expression | `new T`, `::new (p) T(args)` | [[expr.new]] |
| operations that implicitly create objects | `std::malloc`, `std::memcpy`, calling `operator new`, the start of a byte array's lifetime | ¶13–¶16 below |
| implicitly changing the active member of a union | `u.f = 1.0f;` | [[class.union]] |
| creating a temporary object | the `T` materialized in `f(T{})` | [[conv.rval]], [[class.temporary]] |

Operations not on the list do not create objects. `reinterpret_cast<T*>(p)` only changes the type of the pointer; which object the pointer points to generally stays the same ([[expr.reinterpret.cast]]). A non-defining declaration like `extern int x;` creates no object. Note 1 explains that a function is not an object, even though its code occupies storage.

The second half of ¶1 lists the basic properties of objects. An object occupies a region of storage during construction, throughout its lifetime, and during destruction (special rules for construction and destruction are in [[class.cdtor]]). An object can have a name ([[basic.pre]]), and it has a storage duration ([[basic.stc]]) and a type ([[basic.types]]). Note 2 says implementations generate run-time type information for polymorphic objects; this is how the standard refers to the vptr, which `typeid` and `dynamic_cast` rely on.

An object's properties are fixed when it is created, and its type never changes. An `int` object cannot be turned into a `float` object; you can only end the old object's lifetime and create a new `float` object in the same storage ([[basic.life]]).

## Subobjects and complete objects (¶2, ¶5–¶6)

¶2 Objects can contain other objects, called **subobjects**. There are only three kinds: member subobjects (non-static data members, [[class.mem]]), base class subobjects ([[class.derived]]) and array elements. An object that is not a subobject of any other object is a **complete object**.

¶5 Every object x has a **complete object**: x itself if it is a complete object, otherwise the complete object of the object that contains x. Following the subobject relation upward, you reach it.

¶6 If a complete object, member subobject or array element is of class type, its type is the **most derived class**, to distinguish it from the types of base class subobjects. An object of a most derived class type or of non-class type is a **most derived object**. In other words, only base class subobjects are not most derived objects.

The notion of most derived object is used often elsewhere: the dynamic type of an expression is the type of the most derived object it refers to ([[defns.dynamic.type]]); `dynamic_cast<void*>(p)` returns a pointer to the most derived object ([[expr.dynamic.cast]]); virtual bases are initialized by the constructor of the most derived class ([[class.base.init]]).

### Recreating an object in the place of a subobject

If a new `int` is created by placement new in the place of member `a.x`, is the new object a member of `a`, or a separate complete object?

```cpp run title="subobject-replace.cpp" ok
#include <memory>
#include <new>

struct A { int x; int y; };

int main() {
    A a{1, 2};
    std::destroy_at(&a.x);     // ends the lifetime of a.x
    ::new (&a.x) int(3);       // the new int becomes a subobject of a
    return a.x;                // OK: a.x refers to the new object, value 3
}
```

The second half of ¶2 specifies: let e be a subobject (within its lifetime or not), and let a new object be created in the storage of e. If all four of the following hold, the new object is a subobject of the object containing e:

- ¶2.1 the object containing e is within its lifetime;
- ¶2.2 the storage of the new object exactly overlays the storage of e;
- ¶2.3 e is not a potentially-overlapping subobject (see ¶7 below);
- ¶2.4 the new object is of the same type as e (ignoring cv-qualification).

e and the new object are then called **corresponding direct subobjects** ([[g:corresponding-direct-subobjects|corresponding direct subobjects]]). [[basic.life#9]] uses this concept to define transparent replacement: only when these conditions hold does the original name `a.x` automatically refer to the new object.

¶2.3 excludes base class subobjects and `[[no_unique_address]]` members. Their storage may overlap other subobjects, and their tail padding may already be used by other members. Creating an object of complete type in such a place writes `sizeof` of a complete object and may overwrite adjacent members, so the standard does not treat it as a replacement.

## Byte arrays provide storage (¶3–¶4)

What happens if an `int` is created by placement new in a local byte array? Per [[basic.life#2]], when an object's storage is reused by another object, its lifetime ends. Without a special rule, the lifetime of the array `buf` would end there, and accessing it afterward would be a problem.

¶3 gives arrays of `unsigned char` and `std::byte` a privilege. When a complete object is created in the storage of such an array e, if

- ¶3.1 e is within its lifetime,
- ¶3.2 the storage of the new object fits entirely within e,
- ¶3.3 there is no array inside e that is nested more deeply and also satisfies these conditions,

then e is said to **provide storage** ([[g:provides-storage|provides storage]]) for the new object.

¶4 further defines **nested within** ([[g:nested-within|nested within]]): a is nested within b if a is a subobject of b, or b provides storage for a, or they are connected through several steps of such relations (¶4.1–¶4.3).

[[basic.life#2]] specifies that the lifetime of o ends only when its storage is reused by an object not nested within o. When the array provides storage for a new object, the new object is nested within the array, so:

- the array is still within its lifetime;
- the new object exists normally within the array;
- creating another object at the same place ends only the lifetime of the previous nested object (note 3).

`std::optional`, `std::variant`, all kinds of small-buffer optimizations and memory pools are built on this. Here is Example 1 from ¶3:

```cpp run title="provides-storage.cpp" ok
#include <new>

template<class T, class U>
struct AlignedUnion {
    alignas(T) alignas(U) unsigned char data[sizeof(T) > sizeof(U) ? sizeof(T) : sizeof(U)];
};

int f() {
    AlignedUnion<int, char> au;
    int*  p = ::new (au.data) int;        // OK: au.data provides storage for *p
    char* c = ::new (au.data) char();     // OK: ends the lifetime of *p; au.data is unaffected
    char* d = ::new (au.data + 1) char();
    (void)p;
    return *c + *d;                       // OK
}

struct A { unsigned char a[32]; };
struct B { unsigned char b[16]; };
alignas(int) A a;
B*   b = ::new (a.a + 8) B;               // a.a provides storage for *b
int* p = ::new (b->b + 4) int;            // b->b provides storage for *p (¶3.3: the innermost array)
                                          // a.a does not directly provide storage for *p, but *p is nested within a

int main() { return f(); }
```

An object for which an array provides storage is not a subobject of the array; it is a complete object in its own right, merely nested within the array. ¶5 finds the complete object by following only the subobject relation upward, not the provides-storage relation.

!!! pitfall "`char` arrays cannot provide storage"
    ```cpp
    alignas(int) char buf[sizeof(int)];
    int* p = ::new (buf) int(1);
    ```
    Only arrays of `unsigned char` and `std::byte` have this privilege; arrays of `char` and `signed char` do not. Here the `int` reuses the storage of `buf` without being nested within `buf`, so the lifetimes of `buf` and its elements end. As long as `buf` is not used as a `char` array afterward, the program need not have UB, but the semantics are entirely different from providing storage. Always use `unsigned char` or `std::byte` for buffers.

## Object sizes (¶7–¶8)

¶7 There are two kinds of **potentially-overlapping subobject** ([[g:potentially-overlapping-subobject|potentially-overlapping subobject]]): base class subobjects, and non-static data members declared `[[no_unique_address]]` ([[dcl.attr.nouniqueaddr]]). Their storage may overlap other subobjects of the same complete object; in particular they can occupy zero bytes, or give their tail padding to other members.

¶8 An object has nonzero size if any of the following holds:

- ¶8.1 it is not a potentially-overlapping subobject;
- ¶8.2 it is not of class type;
- ¶8.3 it is of a class type with virtual functions or virtual base classes;
- ¶8.4 it has subobjects of nonzero size or unnamed bit-fields of nonzero length.

What remains are potentially-overlapping subobjects of empty class type. If it is a base class subobject of a standard-layout class with no non-static data members, its size is guaranteed to be zero; this is the empty base optimization (EBO) guaranteed by the standard. In other cases, such as `[[no_unique_address]]` members, whether the size is zero is implementation-defined.

```cpp run title="empty-base.cpp" impl
#include <cstdio>

struct Empty {};
struct D : Empty { int x; };                                   // base class subobject: guaranteed zero size
struct M { [[no_unique_address]] Empty e; int x; };            // zero size or not: implementation-defined
struct N { Empty e; int x; };                                  // ordinary member: nonzero size

int main() {
    std::printf("%zu %zu %zu\n", sizeof(D), sizeof(M), sizeof(N));
}
```

Clang 23 prints `4 4 8`. MSVC ignores the standard `[[no_unique_address]]` and requires `[[msvc::no_unique_address]]`; there `M` is usually 8.

An object of nonzero size (other than a bit-field) occupies one or more bytes, including every byte occupied in full or in part by any of its subobjects. The last sentence of ¶8 requires objects of trivially copyable or standard-layout type to occupy contiguous bytes, which is the precondition for `memcpy` of a whole object and for `offsetof`.

## Object addresses (¶9–¶10)

!!! std
    Unless an object is a bit-field or a subobject of zero size, the address of that object is the address of the first byte it occupies.

¶10 Two objects with overlapping lifetimes that are not bit-fields generally have distinct addresses and occupy disjoint bytes. There are only four exceptions:

| Exception | Typical example |
|---|---|
| ¶10.1 one is nested within the other | `&s` and `&s.x` in `struct S { int x; } s;`; a byte array and an object created in it |
| ¶10.2 both are nested within a complete object o, and exactly one is a subobject of o of zero size | an empty base and an object created in a byte array of o |
| ¶10.3 they are subobjects of the same complete object, at least one has zero size, and their types are not similar | an empty base and the first member of the derived class; an empty `[[no_unique_address]]` member and an adjacent member |
| ¶10.4 both are potentially non-unique objects | two string literals with the same content |

¶10.3 requires the types to be not similar ([[conv.qual]]), so two subobjects of the same type never share an address. Checking self-assignment with `this == &other`, and using addresses as object identity, both rely on this.

```cpp run title="no-unique-address.cpp" ok
struct E {};

struct T {
    [[no_unique_address]] E a;
    [[no_unique_address]] E b;   // same type as a, so they cannot share an address
    int x;
};

struct S : E {
    E e;                         // same type as the base E, so they cannot share an address
};

int main() {
    T t;
    S s;
    bool b1 = &t.a != &t.b;                    // always true
    bool b2 = static_cast<E*>(&s) != &s.e;     // always true
    return (b1 && b2) ? 0 : 1;
}
```

The result of `(void*)&t.a == (void*)&t.x` is not guaranteed; on Clang 23 it is true. The address of a subobject of zero size is the address of an unspecified byte occupied by its complete object (the last sentence of ¶10).

### Potentially non-unique objects (¶9)

¶9 The following are **potentially non-unique objects** ([[g:potentially-non-unique-object|potentially non-unique object]]): string literal objects ([[lex.string]]), the backing arrays of initializer lists ([[dcl.init.ref]]), template parameter objects of array type ([[meta.define.static]]), and their subobjects.

Their contents are known at compile time and cannot be modified, and implementations want to merge instances with the same contents, as they have always done with string literals. ¶10.4 allows them to share addresses. Including the backing arrays of `std::initializer_list` in this category came with C++26's [[P2752R3]]: before that, a backing array, like an ordinary temporary array, had to be a distinct object on each evaluation, and `{1, 2, 3}` could not be placed in a shared read-only data section.

Example 2 in ¶10:

```cpp run title="address-identity.cpp" ok
#include <initializer_list>

static const char test1 = 'x';
static const char test2 = 'x';
const bool b = &test1 != &test2;        // always true: two ordinary objects

static const char (&r)[2] = "x";
static const char* s = "x";
static std::initializer_list<char> il = {'x'};
const bool b2 = r != il.begin();        // unspecified: both are potentially non-unique objects
const bool b3 = r != s;                 // unspecified: two string literals may be merged
const bool b4 = il.begin() != &test1;   // always true: test1 is not a potentially non-unique object
const bool b5 = r != &test1;            // always true

int main() {}
```

## Implicit object creation (¶13–¶16) {{c++20}}

### C-style code was UB in C++17

```cpp
struct X { int a, b; };
X* make_x() {
    X* p = (X*)std::malloc(sizeof(X));
    p->a = 1;      // under C++17 rules: UB, p does not point to any X object
    p->b = 2;
    return p;
}
```

Under the C++17 object model, objects could only be created by definitions, new-expressions, union member changes and temporaries. `malloc` was not among them, so the storage `p` points to contained no `X` object, and `p->a` accessed a nonexistent object. By the same reasoning, `memcpy`ing into a raw buffer and then using it as a struct, or `mmap`ing a file and using it as a struct, were both UB. Even typical implementations of `std::vector` had a problem: after `allocate` they do pointer arithmetic on element pointers, but there is no array object there.

C++20's [[P0593R6]] filled this gap, and as a defect report it applies to earlier standards too.

### The rule: objects appear when needed

!!! std
    For each operation that is specified as implicitly creating objects, that operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

¶13 An operation specified as **implicitly creating objects** ([[g:implicitly-create-objects|implicitly creating objects]]) creates zero or more objects of implicit-lifetime types in its region of storage and starts their lifetimes, if doing so would give the program defined behavior.

- Only objects of **implicit-lifetime types** ([[g:implicit-lifetime-type|implicit-lifetime type]], [[basic.types.general]]) are created: scalar types, implicit-lifetime class types, array types, and cv-qualified versions of these. An implicit-lifetime class is roughly an aggregate whose destructor is not user-provided, or a class with at least one trivial eligible constructor and a trivial, non-deleted destructor ([[class.prop]]). `struct { int a, b; }` is one; `std::string` is not. Every array type is one, but note 4 points out that if the elements are not of implicit-lifetime type, their lifetimes do not begin.
- Which objects are created may depend on what happens later. You can imagine the abstract machine foreseeing, at the `malloc`, how the program will use this storage, and creating exactly the objects that make those uses valid.
- If no set of objects would give the program defined behavior, the behavior is undefined; if several would, which set is created is unspecified.
- If the program never uses the storage, no objects need be created at all.

¶14 Some operations are also specified as producing a pointer to a **suitable created object** ([[g:suitable-created-object|suitable created object]]): one of the implicitly created objects whose address is the start of the region is chosen, and a pointer to it is returned, again chosen so that the program has defined behavior. If no such pointer value exists, the behavior is undefined; if several do, which one is chosen is unspecified.

Example 4 in ¶15 is the `make_x` from the beginning. Now `malloc` implicitly creates an `X` and its subobjects `a` and `b`, and returns a pointer to that `X`:

```cpp run title="malloc-x.cpp" ok
#include <cstdlib>

struct X { int a, b; };

X* make_x() {
    X* p = static_cast<X*>(std::malloc(sizeof(X)));   // malloc implicitly creates an X and returns a pointer to it
    p->a = 1;
    p->b = 2;
    return p;
}

int main() {
    X* p = make_x();
    int r = p->a + p->b;
    std::free(p);
    return r == 3 ? 0 : 1;
}
```

Conversely, if later accesses contradict each other, there is no suitable set of objects:

```cpp run title="no-valid-set.cpp" ub
#include <cstdlib>

int main() {
    void* p = std::malloc(sizeof(int));
    *static_cast<int*>(p) = 1;
    float f = *static_cast<float*>(p);   // UB: the same address cannot hold both an int and a float object
    std::free(p);
    return static_cast<int>(f);
}
```

### Which operations implicitly create objects

¶16 specifies two at the language level, neither of which applies during constant evaluation, because constant evaluation must track every object precisely:

- when the lifetime of an array of `unsigned char` or `std::byte` begins, objects are implicitly created in the storage the array occupies, and the array provides storage for them (note 5);
- a call, explicit or implicit, to a function named `operator new` or `operator new[]` implicitly creates objects in the returned storage and returns a pointer to a suitable created object.

Note 6 lists the standard library functions that implicitly create objects:

| Function | Subclause | Effect |
|---|---|---|
| `std::malloc`, `calloc`, `realloc`, `aligned_alloc` | [[c.malloc]] | implicitly create objects and return a pointer to a suitable created object |
| `std::memcpy`, `std::memmove` | [[cstring.syn]] | implicitly create objects in the destination region before copying, and return a pointer to a suitable created object |
| `std::bit_cast` | [[bit.cast]] | implicitly creates nested objects in the result |
| `std::pmr::memory_resource::allocate` | [[mem.res.public]] | same as `operator new` |
| `std::start_lifetime_as`, `start_lifetime_as_array` {{c++23}} | [[obj.lifetime]] | create objects over storage with existing contents, preserving the bytes |

`std::allocator<T>::allocate` obtains storage through `::operator new` and starts the lifetime of a `T[n]` array object, but not of any of its elements ([[allocator.members]]).

### Byte buffers need `std::launder`

The start of a byte array's lifetime implicitly creates objects, but `reinterpret_cast` does not give you a pointer to such an object:

```cpp run title="buffer-launder.cpp" ok
#include <new>

struct P { int x, y; };

int main() {
    alignas(P) unsigned char buf[sizeof(P)];   // buf's lifetime begins, implicitly creating objects (such as a P)

    // P* bad = reinterpret_cast<P*>(buf);
    // bad->x = 1;   // UB: bad still points to buf[0], not to the implicitly created P

    P* p = std::launder(reinterpret_cast<P*>(buf));  // OK: obtains a pointer to the P at that address
    p->x = 1;
    p->y = 2;
    return p->x + p->y == 3 ? 0 : 1;
}
```

`malloc` needs no `launder`, because ¶14 says it returns a pointer to a suitable created object. A byte array has no such return value: the pointer you hold decays from `buf` and points to `buf[0]`. `reinterpret_cast` changes what is pointed to only when the source and target objects are pointer-interconvertible ([[basic.compound]]); an `unsigned char` array and a `P` are not, so the pointer value is unchanged and `std::launder` is needed ([[ptr.launder]]). In practice, mainstream compilers generate the expected code for the version without `launder` too, but the standard does not guarantee it.

### `std::start_lifetime_as` {{c++23}}

The bytes are already in storage (received from the network, `mmap`ed in, written by DMA). How can they be treated as an object without copying?

The C++20 approach is to have the storage copy onto itself: `std::memmove(p, p, n)` implicitly creates objects, preserves the contents, and returns a pointer to them; compilers can usually optimize the copy away. C++23's [[P2590R2]] turned this idiom into a named function: `std::start_lifetime_as<T>(p)` implicitly creates a `T` object at `p` whose object representation is the contents of the storage before the call, and returns a pointer to it ([[obj.lifetime]]).

```cpp title="start-lifetime-as.cpp"
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
    // precondition: packet has sizeof(Header) bytes of storage and satisfies Header's alignment
    return std::start_lifetime_as<Header>(packet);   // no copy: the bytes are the object representation
}
```

At the time of writing, the libc++ we tested does not yet provide `std::start_lifetime_as`; this code has not been verified by compiling, so it carries no verdict.

### Compared with C's effective type rules

C has no notion of creating objects; it handles the same problem with effective types (C17 6.5p6):

| | C | C++ |
|---|---|---|
| storage from `malloc` | has no declared type; the first write with a non-character type makes the written type its effective type | `malloc` implicitly creates exactly the suitable objects right then |
| changing the type | just write with another type | a new object must be created, and the old object's lifetime ends |
| non-trivial types | don't exist | must be constructed explicitly with a new-expression |

For trivial data the two languages largely agree, and assigning to members after `malloc` is valid in both. But in C, writing determines the type; in C++, the object exists first and is then written to. In C++ the value of a pointer (which object it points to) is meaningful, which is why C++ has `std::launder` and C does not.

## Constituent values in constant evaluation (¶11–¶12)

These two paragraphs are new wording after C++23, serving the checks on constant expressions ([[expr.const]]).

¶11 The direct members of a union, and the elements of arrays that are themselves such members, are **union elemental subobjects**; a union elemental subobject not within its lifetime is inactive.

¶12 The **constituent values** ([[g:constituent-values|constituent values]]) of an object: for a scalar object, its value; for other objects, the constituent values of all its direct subobjects, skipping inactive union elemental subobjects. **Constituent references** are defined similarly: the direct members of reference type plus the constituent references of the subobjects.

[[expr.const]] requires the constituent values and constituent references of the result of a constant expression to satisfy certain conditions, for example not being indeterminate or erroneous values. Because inactive union elements are skipped, a `constexpr` union only needs its active part initialized. When only some elements of an array member are within their lifetimes (with the help of `std::start_lifetime` in [[obj.lifetime]]), only those elements are checked.

```cpp
struct A {
    struct X { int i; int j; };
    struct Y { X x1; X x2; };
    union { int i; int arr[4]; Y y; };
};

constexpr A v2{.i = 1};  // OK: the constituent values are {v2.i}
constexpr A v4 = [] {
    A a;
    a.y.x1.i = 1;        // changes the active member to y
    a.y.x2.j = 2;
    return a;
}();                     // error: the constituent values include the uninitialized v4.y.x1.j and v4.y.x2.i
```

This code is adapted from Example 3 in ¶12 and carries no verdict, because the standard's example disagrees with the normative wording. Example 3 also has a line `constexpr A v1;` marked OK. Clang 23 rejects that line: default-initializing a const object requires the type to be const-default-constructible, and [[dcl.init.general#7]] requires an anonymous union to have exactly one member with a default member initializer, which `A` does not satisfy. Per the normative wording, Clang is right. For `v4`, Clang's diagnostic agrees with the standard's example. The part of Example 3 that uses `std::start_lifetime(a.arr)` is omitted here, because the libc++ we tested does not yet provide that function.

## Implementation view

!!! impl "How compilers see the object model"
    - The object model is nearly invisible in machine code. Its role is to constrain programs, thereby leaving room for the optimizer. For example, type-based alias analysis (TBAA) assumes `int*` and `float*` do not point to the same object, which corresponds exactly to the case above where having no suitable set of objects is UB.
    - Implicit object creation has almost no code-generation cost; compilers already treat `malloc` and `memcpy` as operations that may write any type.
    - GCC and Clang implement `std::launder` with the builtin `__builtin_launder`, which prevents the optimizer from inferring that the object this pointer points to has not changed, particularly for cached `const` members and vptrs.
    - Under the Itanium ABI, an empty base is placed at offset 0, at the same address as the first member, when there is no conflict; when the first member is an empty class of the same type, the base is moved away to satisfy ¶10.3.

## History

!!! history
    - C++98/03 defined an object as "a region of storage", leaving behind the view that storage means an object, and plenty of ambiguity.
    - C++17's [[P0137R1]] rewrote the object model: objects are created by listed constructs, and it introduced providing storage, nested within, pointers pointing to objects, and `std::launder`. A side effect was that C-style code like `malloc` followed by member assignment became clearly UB.
    - C++20's [[P0593R6]] introduced implicit object creation and implicit-lifetime types, fixing that problem, and applies to earlier standards as a defect report. Potentially-overlapping subobjects arrived at the same time, with `[[no_unique_address]]`.
    - C++23's [[P2590R2]] added `std::start_lifetime_as` and `start_lifetime_as_array`.
    - C++26's [[P2752R3]] made the backing arrays of initializer lists potentially non-unique objects.

## Common misconceptions

!!! pitfall "`reinterpret_cast` creates an object"
    `reinterpret_cast<T*>(p)` only changes the type of the pointer. If there is no `T` object at `p`, or there is one but `p` does not point to it, accessing through the result is UB. The right approaches are creating the object with placement new, relying on implicit object creation plus `std::launder`, using `std::start_lifetime_as`, or copying into a local variable with `std::memcpy` or `std::bit_cast`.

!!! pitfall "Implicit object creation works for all types"
    It creates only objects of implicit-lifetime types. `std::string* s = (std::string*)malloc(sizeof(std::string)); *s = "x";` is still UB: `std::string` has a non-trivial constructor and destructor, `malloc` does not create one, and you must use `::new (raw) std::string`.

!!! pitfall "Two empty members of the same type can share an address"
    ¶10.3 requires the types to be not similar. Two `[[no_unique_address]] Empty` members cannot share an address. Attempts to shrink an object with several empty members of the same type (such as several `std::allocator`s) often fail to achieve the goal.

## Questions

!!! question "Question 1"
    Does the program below have defined behavior? If so, which objects does `malloc` implicitly create?

    ```cpp
    #include <cstdlib>
    int main() {
        int* p = static_cast<int*>(std::malloc(4 * sizeof(int)));
        for (int i = 0; i < 4; ++i) p[i] = i;
        int s = p[0] + p[3];
        std::free(p);
        return s;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It has defined behavior. `p[i]` is `*(p + i)`, and for `i` greater than 1, [[expr.add]] requires `p` to point to an element of some array. So `malloc` must implicitly create an `int[4]` array object (array types are implicit-lifetime types) and the 4 `int` elements in it.

The returned pointer is chosen by ¶14. There are two candidate objects at the start of the region: the array itself and its first element. They are not pointer-interconvertible, and the value after `static_cast<int*>` must point to an `int`, so the suitable one is the first element. This is the mechanism that makes `std::vector`-style code valid.
</details>

!!! question "Question 2"
    Given `struct A { unsigned char buf[8]; } a;`, after placement new of an `int` into `a.buf`, has the lifetime of `a` ended? What about `struct B { char buf[8]; } b;`?

<details markdown="1">
<summary>Answer</summary>

For `A`, no. `a.buf` provides storage for the `int` (¶3), and the `int` is nested within `a.buf` and hence within `a` (¶4). By item 2.5 of [[basic.life#2]], the lifetime of o ends only when its storage is reused by an object not nested within o, so `a` and `a.buf` are both still within their lifetimes.

For `B`, yes. A `char` array cannot provide storage, and the new `int` is not nested within `b` or `b.buf`. It reuses the storage of 4 elements of `b.buf` and part of the storage of `b`, so the lifetimes of those elements, of `b.buf` and of `b` itself all end. Accessing through `b` afterward falls into the undefined behavior listed in [[basic.life#8]].
</details>
