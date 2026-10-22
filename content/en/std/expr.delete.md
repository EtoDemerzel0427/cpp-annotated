---
title: The delete expression
summary: delete and delete[] first destroy the object and then call a deallocation function; this page covers which pointers may be deleted, why a base class needs a virtual destructor, which operator delete is called, and what arguments it receives.
updated: 2026-10-19
---

!!! tldr
    - `delete p` does two things: calls the destructor, then calls the deallocation function `operator delete` to return the storage. `delete[]` does the same for an array, destroying elements in the reverse order of construction.
    - `delete` may only be used on the result of a non-array `new`, `delete[]` only on the result of an array `new`, and both accept a null pointer; using the wrong one is undefined behavior.
    - When deleting a derived-class object through a base-class pointer, the base class must have a virtual destructor, or the behavior is undefined. Deleting an array of derived objects through a base-class pointer with `delete[]` is UB even with a virtual destructor.
    - Since C++26, `delete` on a pointer to an incomplete class is ill-formed; previously it could silently skip the destructor.
    - Deallocation function selection follows a fixed order: destroying ones first, then filtering by alignment; in class scope the unsized version is preferred, and in global scope the sized version is preferred when the type is complete.

## What delete does (¶1)

¶1 A *delete-expression* destroys a most derived object or array created by a *new-expression*. It mirrors `new` ([[expr.new]]) and also has two steps:

1. call the destructor (if any);
2. call the **deallocation function** `operator delete` or `operator delete[]` to return the storage ([[basic.stc.dynamic.deallocation]]).

`delete cast-expression` is a **single-object delete expression** ([[g:single-object-delete-expression]]), and `delete [] cast-expression` is an **array delete expression** ([[g:array-delete-expression]]); both may be preceded by `::`. The type of the expression is `void`.

```cpp title="delete-operand.cpp" run ok
struct Handle { int* p; operator int*() const { return p; } };

int main() {
    const int* c = new const int(1);
    delete c;                                  // OK: a pointer to const can be deleted too
    int* n = nullptr;
    delete n;                                  // OK: null pointer
    Handle h{new int(2)};
    delete h;                                  // OK: contextually implicitly converted to int*
    delete ([] { return new int(3); })();      // OK: the lambda is parenthesized
}
```

If the operand has class type, it is contextually implicitly converted ([[conv]]) to a pointer to object type, which requires the class to have exactly one such non-explicit conversion function. Otherwise the operand must be a prvalue of pointer to object type; neither `void*` nor function pointers will do:

```cpp title="delete-operand-error.cpp" error
void f(void* vp, void (*fp)()) {
    delete vp;                         // error: void isn't an object type
    delete fp;                         // error: function pointer
    delete [] { return new int; }();   // error: [] is interpreted as delete[]
}
```

Empty square brackets right after `delete` are always interpreted as the array form, so a lambda starting with `[]` must be parenthesized (footnote 55). For `delete vp` in C++23 mode, Clang 23 accepts it with just a `-Wdelete-incomplete` warning; it has always been ill-formed, and the warning satisfies the diagnostic requirement.

Deleting a pointer to `const` doesn't need a `const_cast` first (Note 2). Destruction doesn't count as modification; a local `const` object is also destroyed when it goes out of scope.

## Which pointers may be deleted (¶2)

```cpp title="delete-mismatch.cpp" run ub
int main() {
    int* p = new int[4];
    delete p;           // UB: an array new must use delete[]
}
```

¶2 specifies what the value of the operand may be; anything else is UB:

| Form | The operand may be |
|---|---|
| `delete p` | a null pointer; the result of a non-array *new-expression*; or a pointer to a base class subobject of an object created that way |
| `delete[] p` | a null pointer; the result of an array *new-expression* that didn't use the non-allocating placement form `new (buf) T[n]` |

Note 1 points out that the choice of form depends on the type of the allocated object, not on how the `new` was written: `using A = int[4]; int* p = new A;` must use `delete[] p`. Footnote 56 adds that a zero-length array has no first element, but its `new` result must still be released with `delete[]`.

For the example above, Clang gives a `-Wmismatched-new-delete` warning at compile time; at run time, with `ASAN_OPTIONS=alloc_dealloc_mismatch=1` set (off by default on macOS), AddressSanitizer reports `alloc-dealloc-mismatch (operator new [] vs operator delete)`.

Other common violations:

- deleting the address of a stack or static object;
- deleting the address of an element in the middle of an array or of a member subobject;
- deleting twice: after the first `delete`, every pointer to the object becomes an invalid pointer value ([[basic.stc.dynamic.deallocation]]);
- using `delete[]` on an array created by `new (buf) T[n]`. That storage wasn't allocated by `operator new[]`; destroy the elements one by one instead, for example with `std::destroy_n`.

## Base-class pointers and virtual destructors (¶3)

```cpp title="no-virtual-dtor.cpp" run ub
struct B { ~B() {} };                        // non-virtual destructor
struct D : B {
    int* buf = new int[4];
    ~D() { delete[] buf; }
};
int main() {
    B* p = new D;
    delete p;    // UB: static type B differs from dynamic type D, and B has no virtual destructor
}
```

¶3 For a single-object `delete`: if the static type of the object to be deleted (the type the pointer was declared with) isn't similar ([[conv.qual]], that is, differs other than in cv-qualification at each level) to its dynamic type (the type actually created), and the selected deallocation function isn't a destroying operator delete (see below), then the static type must be a base class of the dynamic type and must have a virtual destructor, or the behavior is undefined.

In our tests this program calls only `~B()`; `~D()` is skipped, `buf` leaks, and LeakSanitizer reports a 16-byte leak. But the consequences go beyond a leak: the size passed to a sized `operator delete` is `sizeof(B)`; with multiple inheritance the `B*` doesn't even equal the starting address of the object, so the deallocation function receives the wrong pointer.

For an array `delete[]`, a static type not similar to the dynamic type is UB outright, with no virtual-destructor exception:

```cpp title="polymorphic-array.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra; };
int main() {
    B* a = new D[2];
    delete[] a;    // UB: the array's static type B isn't similar to its dynamic type D
}
```

`delete[]` must walk the array by element size; the element stride is `sizeof(D)`, but through a `B*` only `sizeof(B)` is known, and a virtual destructor can't fix the stride.

## Incomplete types (¶4) {{c++26}}

```cpp title="delete-incomplete.cpp" error
struct Inc;
void f(Inc* p) {
    delete p;    // error: deleting a pointer to an incomplete type (C++26)
}
```

¶4 If the object being deleted has incomplete class type at the point of `delete`, the program is ill-formed.

This is a C++26 change ([[P3144R2]]). The previous rule was: if the complete type has a non-trivial destructor or a class-specific deallocation function, the behavior is undefined. The compiler can't see the destructor at the point of `delete`, so all it can do is not call it and then call the global `operator delete`; the program compiles, but the destructor never runs. Clang 23 reports `cannot delete pointer to incomplete type 'Inc'` under `-std=c++2c`, and only gives a `-Wdelete-incomplete` warning under `-std=c++23`.

The default deleter of `std::unique_ptr<T>` has always required `T` to be complete ([[unique.ptr.dltr.dflt#3]]), which is why the pimpl idiom defines the destructor in the `.cpp` file where `Impl` is complete.

## Destruction (¶5)

¶5 If the operand isn't a null pointer and the selected function isn't a destroying operator delete, `delete` invokes the destructor (if any) of the object or of the array elements. The destructor must be accessible at the point of `delete`. Array elements are destroyed in order of decreasing address, that is, the reverse of the order in which their construction completed.

```cpp title="delete-private-dtor.cpp" error
struct Priv {
private:
    ~Priv();
};
void f(Priv* p) {
    delete p;    // error: the destructor is inaccessible
}
```

Making the destructor private or protected forces objects to be destroyed only through a particular interface, such as the `release()` of a reference-counted class.

## Null pointers and calling the deallocation function (¶6)

¶6 If the operand isn't a null pointer, `delete` calls the deallocation function, with the value originally returned by the allocation function as its first argument. Note 3 adds that the deallocation function is called even if the destructor throws an exception.

If the operand is a null pointer, it is unspecified whether the deallocation function is called. The destructor is certainly not called; if the deallocation function is called, it receives a null pointer, and the standard library's versions do nothing with a null pointer ([[new.delete.single]]). So the check in `if (p) delete p;` is redundant, and a custom `operator delete` must handle a null pointer.

```cpp title="delete-null.cpp" ok
struct S { ~S() {} };
void f() {
    S* p = nullptr;
    delete p;          // OK: ~S() isn't called; operator delete may or may not be called
    delete[] p;        // OK: likewise
}
```

¶6.2 and ¶6.3 cover another situation: an implementation may omit the allocation call of a `new`, or merge the allocations of several `new`s into one ([[expr.new#14]]). In that case the deallocation function is called once, only after every object sharing that storage has been deleted; if the allocation was omitted, it isn't called.

## Which deallocation functions are found (¶7–¶8)

¶7 A single-object `delete` calls `operator delete`, an array `delete` calls `operator delete[]`. The standard library provides global versions, which a program may replace ([[replacement.functions]]); a class may also provide class-specific versions ([[class.free]]).

¶8 If the `delete` isn't preceded by `::` and the operand points to a class type `T` or an array of `T`:

- ¶8.1 for a single-object `delete` where `T` has a virtual destructor: the deallocation function selected at the point of definition of the dynamic type's virtual destructor is used ([[class.dtor]]);
- ¶8.2 otherwise lookup is performed in the scope of `T`.

In all other cases, including when `::` was written, when the type isn't a class type, or when nothing is found in class scope, lookup is in the global scope. Of the declarations found, only **usual deallocation functions** ([[basic.stc.dynamic.deallocation]]) are kept, that is, versions with parameters like `(void*)`, `(void*, std::size_t)`, `(void*, std::align_val_t)` and so on; placement forms are discarded.

Note 5: if the class has only placement deallocation functions, the set is empty after discarding them and the program is ill-formed; there is no fallback to global scope, because lookup has already found declarations in the class.

```cpp title="only-placement-delete.cpp" error
#include <cstddef>
struct OnlyPlacement {
    static void* operator new(std::size_t, int);
    static void operator delete(void*, int);   // placement form only
};
void g(OnlyPlacement* p) {
    delete p;    // error: all declarations found in the class are discarded
}
```

¶8.1 makes virtual destructors and class-specific `operator delete` work together correctly: when a `Derived` object is deleted through a `Base*`, the deallocation function from `Derived`'s scope is used, and `Derived`'s size is passed.

```cpp title="virtual-dtor-dealloc.cpp" run ok
#include <cstdio>
#include <new>

struct Base {
    virtual ~Base() = default;
};
struct Derived : Base {
    double payload[4];
    static void operator delete(void* p, std::size_t n) {   // class-specific, sized
        std::printf("Derived::operator delete(p, %zu)\n", n);
        ::operator delete(p);
    }
};

int main() {
    Base* b = new Derived;
    delete b;   // selects Derived::operator delete, with size sizeof(Derived)
}
```

On a 64-bit platform it prints `Derived::operator delete(p, 40)`.

## Which deallocation function is selected (¶9)

¶9 Given the set of usual deallocation functions found by lookup, they are filtered in turn:

| Step | Rule |
|---|---|
| ¶9.1 | if there is a destroying operator delete, all non-destroying ones are eliminated |
| ¶9.2 | if the type has new-extended alignment, functions with a `std::align_val_t` parameter are preferred, otherwise those without one; if any are preferred, the rest are eliminated |
| ¶9.3 | if exactly one remains, it is selected |
| ¶9.4 | if the deallocation functions belong to a class scope, the one without a `std::size_t` parameter is selected |
| ¶9.5 | if the type is complete, the one with a `std::size_t` parameter is selected; for an array `delete`, the element type must also be a class with a non-trivial destructor |
| ¶9.6 | otherwise it is unspecified whether the version with `std::size_t` is selected |

Unless the deallocation function was selected at the point of definition of the dynamic type's virtual destructor (¶8.1), it must be accessible at the point of `delete`.

```cpp title="sized-dealloc-selection.cpp" run ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n) { return std::malloc(n ? n : 1); }
void operator delete(void* p) noexcept { std::puts("global unsized"); std::free(p); }
void operator delete(void* p, std::size_t n) noexcept { std::printf("global sized %zu\n", n); std::free(p); }

struct Both {
    static void operator delete(void* p) { std::puts("Both: unsized"); ::operator delete(p); }
    static void operator delete(void* p, std::size_t) { std::puts("Both: sized"); ::operator delete(p); }
};

int main() {
    delete new int;    // global, complete type: ¶9.5, sized
    delete new Both;   // the class has both: ¶9.4, unsized
}
```

Clang 23 prints `global sized 4`, `Both: unsized`, `global unsized`. Compiled with `-fno-sized-deallocation`, the first line becomes `global unsized`.

The two rules point in opposite directions for compatibility. A class-specific `operator delete(void*, std::size_t)` has been valid since C++98, and when a class declared both versions the one-parameter one was always used; C++14 couldn't change the behavior of existing programs. The global sized version was new in C++14 ([[N3778]]), so it could simply specify that the size is passed whenever it can be, which saves allocators like tcmalloc and jemalloc from looking up the block size on deallocation.

For arrays the sized version is required only when the element has a non-trivial destructor, because only then does `new[]` record the element count (the array cookie), so that `delete[]` can compute the total size. `-fno-sized-deallocation` violates ¶9.5, but is useful for compatibility with old allocators that don't provide sized versions.

## Arguments passed to the deallocation function (¶10)

¶10 First the **deleted object** ([[g:deleted-object]]) is defined: in a single-object `delete`, if the static type of the object *A* pointed to by the operand has no virtual destructor, the deleted object is *A*, otherwise it is the most derived object of *A*; in an array `delete` it is the whole array object.

| Parameter | Argument |
|---|---|
| the first (`void*`, or `T*` for a destroying one) | the address of the deleted object; for arrays, adjusted by the allocation overhead, i.e. moved back before the cookie |
| `std::destroying_delete_t` | an unspecified value |
| `std::align_val_t` | the alignment of the deleted object's type |
| `std::size_t` | the size of the deleted object; for arrays, the size of the array plus the allocation overhead |

Note 7: cv-qualification is ignored when forming the first argument, so a value of type `const S*` can be passed directly to a `void*` parameter.

Note 8: if a replaceable standard deallocation function is called, the pointer, size and alignment passed must match those of the original allocation, or the behavior is undefined ([[new.delete.single]]). Deleting an object through a base-class pointer without a virtual destructor corrupts the allocator in practice, and a wrong size is one of the reasons.

## Destroying operator delete {{c++20}}

A **destroying operator delete** ([[P0722R3]]) is a class-specific `operator delete` whose first parameter is `C*` rather than `void*` and whose second parameter has type `std::destroying_delete_t` ([[basic.stc.dynamic.deallocation]]). When it is selected:

- `delete` doesn't call the destructor (¶5); destruction is its own responsibility;
- the virtual destructor required by ¶3 is no longer needed; it determines the dynamic type itself;
- it receives a typed pointer to the object, and the object is still alive at that point.

The following example implements polymorphic deletion with a type tag instead of a vtable:

```cpp title="destroying-delete.cpp" run ok
#include <cstdio>
#include <new>

struct Shape {
    enum Kind { circle, square } kind;
    explicit Shape(Kind k) : kind(k) {}
    void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; Circle() : Shape(circle), r(1) {} ~Circle() { std::puts("~Circle"); } };
struct Square : Shape { double a; Square() : Shape(square), a(2) {} ~Square() { std::puts("~Square"); } };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    switch (p->kind) {        // the object is still alive, so kind can be read
    case circle: { auto* c = static_cast<Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(Circle)); break; }
    case square: { auto* s = static_cast<Square*>(p); s->~Square(); ::operator delete(s, sizeof(Square)); break; }
    }
}

int main() {
    Shape* a = new Circle;
    Shape* b = new Square;
    delete a;   // OK: no virtual destructor, but a destroying delete is selected
    delete b;
}
```

Another use is objects with variable-length trailing data, where the allocation size is recorded in a field of the object itself. When an ordinary `operator delete` is called the object has already been destroyed and the field can't be read; a destroying version can read the size first, then destroy and deallocate.

## delete this

The standard doesn't forbid `delete this`. By ¶2, `delete this` is defined as long as `*this` is a most derived object created by a non-array `new`. The restrictions afterwards come from [[basic.life]] and [[basic.stc.dynamic.deallocation]]:

- no non-static member may be accessed and no non-static member function called afterwards, since the object is no longer within its lifetime;
- the value of `this` becomes an invalid pointer value, and even copying it is implementation-defined behavior;
- calling a member function that does `delete this` on a stack or static object is UB.

```cpp title="delete-this.cpp" run ok
#include <cstdio>
struct Node {
    int refs = 1;
    void release() {
        if (--refs == 0) delete this;   // OK: created by non-array new, no member access afterwards
    }
    ~Node() { std::puts("~Node"); }
};
int main() {
    Node* n = new Node;
    n->release();    // n is an invalid pointer value afterwards
}
```

!!! impl
    - The Itanium C++ ABI puts two destructors in the vtable for a class with a virtual destructor: the complete object destructor D1 only destroys; the deleting destructor D0 destroys and then calls `operator delete`. `delete pb` compiles to a virtual call to D0; the deallocation function that ¶8.1 says is selected at the point of definition of the dynamic type's destructor is the one called inside D0, and `sizeof(Derived)` is determined there too.
    - MSVC uses a scalar deleting destructor, with a flag parameter that decides whether to deallocate after destruction; arrays have a separate vector deleting destructor.
    - When the base class has no virtual destructor, the compiler calls `B::~B()` directly and then calls `operator delete` with the value of the `B*` and `sizeof(B)`. Under single inheritance the base class subobject is usually at offset 0, so it appears to work; under multiple inheritance the pointer value is wrong and the heap gets corrupted.
    - Sized deallocation: Clang enables it by default since version 19, GCC enables it by default in C++14 and later modes, and MSVC also enables it by default.
    - GCC and Clang both check for a null pointer first in a single-object `delete`; if it is null they neither destroy nor call `operator delete`, which ¶6 allows.

## History

!!! history
    - C++98 already had the `delete`/`delete[]` pairing rules, the need for a virtual destructor in the base class, and deletion of incomplete types (UB when the destructor is non-trivial).
    - C++14 introduced sized deallocation ([[N3778]]), giving the sized versus unsized selection rules in ¶9.
    - C++17 introduced aligned deallocation functions ([[P0035R4]], ¶9.2).
    - C++20 introduced destroying operator delete ([[P0722R3]]).
    - C++26 made deleting an incomplete type ill-formed ([[P3144R2]]).
    - The post-C++26 draft makes a program ill-formed if a deallocation function has a potentially-throwing exception specification ([[diff.cpp26]]) {{c++29}}. Previously a deallocation function without a *noexcept-specifier* was already implicitly `noexcept`, but explicitly writing `noexcept(false)` was allowed.

## Common misconceptions

!!! pitfall "The destructor of a polymorphic base class doesn't need to be virtual"
    Whenever a derived-class object might be deleted through a base-class pointer, the base class needs a virtual destructor, or a destroying delete instead. The common guideline: the destructor of a polymorphic base class is either `public virtual` or `protected` non-virtual; the latter makes code that deletes through a base-class pointer fail at compile time.

!!! pitfall "`delete p; p = nullptr;` prevents all double deletes"
    It protects only that one variable. Other pointers to the same object, including `this`, are still invalid pointer values.

!!! pitfall "A custom `operator delete` doesn't need to handle a null pointer"
    Whether the deallocation function is called for a null pointer is unspecified (¶6), so an implementation may call your class-specific version with a null pointer.

## Questions

!!! question "Question 1"
    ```cpp
    struct B { virtual ~B(); static void operator delete(void*); };
    struct D : B { static void operator delete(void*, std::size_t); };
    B* p = new D;
    delete p;
    ```
    Which deallocation function is called? With what arguments?

<details markdown="1">
<summary>Answer</summary>

`B` has a virtual destructor, so by ¶8.1 the deallocation function is selected at the point of definition of `D`'s implicit virtual destructor: lookup in `D`'s scope finds `D::operator delete(void*, std::size_t)`, which hides `B`'s version. There is only one candidate, so it is selected by ¶9.3.

The deleted object is the most derived object, so the arguments are the address of the `D` object and `sizeof(D)` (¶10). Because it is selected at the point of definition of the virtual destructor, the accessibility requirement in the last sentence of ¶9 isn't checked at `delete p`.
</details>

!!! question "Question 2"
    Is `struct T { int x; }; const T* q = new const T[2]{{1}, {2}}; delete[] q;` valid? What is passed to `operator delete[]`?

<details markdown="1">
<summary>Answer</summary>

Valid. Note 2 allows deleting a pointer to `const`, and Note 7 says cv-qualification is ignored when forming the argument. `T`'s destructor is trivial, so implementations usually don't add an array cookie, and the address adjusted by the overhead is `q` itself; if the sized version is called, the size is `2 * sizeof(T)` plus the overhead.

Note that `new const T[2]` without an initializer is ill-formed: default-initializing a `const` object requires the type to be const-default-constructible, and `T`'s `x` has no default member initializer.
</details>

## Summary

| Question | Paragraph | Answer |
|---|---|---|
| Operand | ¶1 | a prvalue of pointer to object type, or a class contextually convertible to one; `delete []` is always the array form |
| Valid values | ¶2 | a null pointer, or the result of the corresponding form of `new` (for single objects also a pointer to a base class subobject); otherwise UB |
| Static and dynamic type | ¶3 | single object: if not similar, a virtual destructor is required, except with a destroying delete; array: not similar is UB |
| Incomplete type | ¶4 | ill-formed (C++26) |
| Destruction | ¶5 | called if non-null and not a destroying delete, must be accessible; arrays in reverse order |
| Deallocation | ¶6 | called if non-null; unspecified for a null pointer |
| Lookup | ¶8 | with a virtual destructor, the one selected at the dynamic type's destructor; otherwise class scope, then global; only usual deallocation functions are kept |
| Selection | ¶9 | destroying > alignment match > unique > class scope takes unsized > complete type takes sized > unspecified |
| Arguments | ¶10 | address of the deleted object (adjusted for arrays), alignment, size (arrays include the overhead) |
