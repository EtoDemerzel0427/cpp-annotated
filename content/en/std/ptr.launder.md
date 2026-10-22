---
title: "Pointer optimization barrier: std::launder"
summary: "The contract of std::launder: given a pointer with the right address but pointing to an old object (or to storage rather than an object), it returns a pointer to the object now at that address; it doesn't create objects and can't widen the range a pointer can reach."
updated: 2026-10-19
---

!!! tldr
    - A pointer isn't just an address; it points to a particular object. After a new object is created where an old one was, old pointers usually point to the new object automatically, but there are exceptions; `std::launder` handles those exceptions.
    - Typical places that need it: replacing a const complete object, replacing a base class subobject, and getting an object pointer from an `unsigned char` buffer with `reinterpret_cast`.
    - Preconditions: there must already be an object of similar type, within its lifetime, at the address, and the result must not be able to reach more bytes than the original pointer. Violations are undefined behavior.
    - If `T` is a function type or `void`, the program is ill-formed. `launder` generates no machine instructions; it only constrains the optimizer.

## Why it is needed

```cpp run title="launder-const.cpp" ok
#include <new>

struct X { int n; };

int main() {
  const X* p = new const X{3};
  const int a = p->n;
  new (const_cast<X*>(p)) const X{5};  // the complete object is const: p doesn't point to the new object
  // const int b = p->n;               // UB
  const int c = std::launder(p)->n;    // OK, c == 5
  delete std::launder(p);
  return a + c == 8 ? 0 : 1;
}
```

This is the example in paragraph 6 of the standard (with `delete` added). A C++ pointer value points to a specific object, not just an address ([[basic.compound]]). For two objects that exist one after the other at the same address, the pointer values pointing to them are different.

In most cases, after a new object of the same type is created in the storage of an old one, old pointers automatically point to the new object; this is called **transparent replacement** ([[g:transparently-replaceable]], [[basic.life#9]]). But when the old object is a const complete object, transparent replacement doesn't apply: `p` still points to the old object, whose lifetime has ended, and reading `n` through it is undefined behavior. The compiler may therefore assume `p->n` is still 3.

`std::launder(p)` returns a pointer to the object currently at that address (the new `X{5}`). The full conditions for transparent replacement and more examples are in [[basic.life]].

¶5 Note 1 summarizes when `launder` is needed: if a new object is created in storage occupied by an existing object of the same type, a pointer to the original object can be used to refer to the new object, unless its complete object is a const object or it is a base class subobject; in those two cases, use `launder`.

| Scenario | Why the old pointer can't be used |
|---|---|
| Replacing a const complete object | Transparent replacement requires the old object not to be a const complete object ([[basic.life#9]]) |
| Replacing a base class subobject | Base class subobjects may overlap other objects and don't take part in transparent replacement ([[intro.object#2]]) |
| Getting an object pointer from a byte buffer with `reinterpret_cast` | The result of the cast still points to the buffer array, not to the object created in it (providing storage in [[intro.object]]) |
| The new object has a different type | Transparent replacement requires the same type (ignoring top-level cv) |

The third is the most common in real code; hand-written `optional`, `variant` and small-buffer optimizations all run into it:

```cpp run title="launder-buffer.cpp" ok
#include <new>
#include <string>

template<class T>
class Slot {
  alignas(T) unsigned char buf_[sizeof(T)];
public:
  template<class... A> void emplace(A&&... a) {
    ::new (buf_) T(static_cast<A&&>(a)...);
  }
  T& get() {   // launder is required: the cast result still points to buf_
    return *std::launder(reinterpret_cast<T*>(buf_));
  }
  void reset() { get().~T(); }
};

int main() {
  Slot<std::string> s;
  s.emplace("hello");
  bool ok = s.get() == "hello";
  s.reset();
  return ok ? 0 : 1;
}
```

An alternative is to save the pointer returned by placement new in `emplace` and always use it afterwards; then `launder` isn't needed, at the cost of storing an extra pointer.

## Signature and Mandates (¶1)

```cpp
template<class T> constexpr T* launder(T* p) noexcept;
```

¶1 Mandates: `!is_function_v<T> && !is_void_v<T>` is `true`. Mandates in a library clause means the program is ill-formed if the condition isn't met, and the compiler must diagnose it ([[structure.specifications]]).

```cpp title="launder-mandates.cpp" error
#include <new>

void f();
auto p = std::launder(&f);   // error: T is a function type
auto q = std::launder(static_cast<void*>(nullptr));  // error: T is void
```

Functions aren't objects, so there is no such thing as creating a new function in a function's storage; a `void*` doesn't point to an object of a particular type, so `launder` would have no idea which object to look for. Clang 23 reports "function pointer argument to '__builtin_launder' is not allowed" and "void pointer argument ..." for the two lines respectively.

## Preconditions (¶2)

¶2 has three Preconditions, and violating any of them is undefined behavior:

1. `p` represents the address *A* of a byte in memory. Null pointers and invalid pointer values don't qualify, so `std::launder(nullptr)` is undefined behavior, even though in practice it does nothing.
2. An object *X* whose type is similar to `T` (differing only in cv-qualification; see [[conv.qual]]) is located at address *A*, and *X* is within its lifetime or is an array element of an array object within its lifetime. The second half covers cases like `std::allocator<T>::allocate`: the array exists and the elements' lifetimes haven't begun, but pointers to elements are still needed.
3. Every byte that would be reachable through the result is reachable through `p`.

Item 2 means `launder` doesn't create objects or begin anyone's lifetime. When the address holds only an `unsigned char` buffer and no `T` object, create the object first: by implicit object creation or `std::start_lifetime_as` ([[obj.lifetime]]).

What item 3 calls reachable is defined in [[basic.compound]]. The bytes reachable through a pointer to an object *x* are the storage occupied by *x*, or, if *x* is an array element, the storage occupied by the whole array (the precise definition also takes into account objects pointer-interconvertible with *x*). This item prevents using `launder` to escape the bounds of pointer arithmetic:

```cpp run title="launder-reachability.cpp" ub
#include <new>

int arr[2][3];

int main() {
  int* p = &arr[0][0];   // reachable through p: the 12 bytes of arr[0]
  auto q = std::launder(reinterpret_cast<int(*)[3]>(p));
  // q would point to arr[0]; reachable through it: all of arr (24 bytes)
  return q[1][0];        // UB: violates the reachability requirement of ¶2
}
```

`arr[0]` is itself an element of the array `arr`, so a pointer to it can move to `arr[1]`; but `arr[0][0]`, which `p` points to, can only move within `arr[0]`. The compiler may assume that only these 12 bytes are accessed through `p`, and `launder` can't break that assumption. In our tests this example runs without any symptom, and the sanitizers report nothing.

## Return value and constant evaluation (¶3–¶4)

¶3 Returns: a value of type `T*` that points to *X*.

¶4 In a constant expression, a call to `launder` is a core constant expression only if the argument itself could be used in place of the call. In other words, `launder` during constant evaluation can only be an identity transformation. The constant evaluator knows which object every pointer points to, so stale pointers needing correction never arise; if the argument doesn't point to *X*, the call isn't a constant expression.

## Implementation

!!! impl "libc++: a single built-in"
    libc++'s `std::launder` is just `return __builtin_launder(__p);`, and the Mandates of paragraph 1 are checked by this built-in.

    `__builtin_launder` generally generates no instructions. In the intermediate representation, it cuts the link between the result pointer and the original pointer, so the optimizer can no longer apply values learned through the original pointer (such as the old value of a const member) to reads through the result pointer. With `-fstrict-vtable-pointers`, Clang also treats it as a barrier for its assumption that vtable pointers don't change.

!!! pitfall "Errors `launder` can't fix"
    - When there is no object at the address, it doesn't create one.
    - It can't widen the reachable range; it can't turn an element pointer into a pointer to the whole array.
    - It can't fix type errors: `std::launder(reinterpret_cast<float*>(&i))` has no `float` object at `&i`, so the precondition isn't met.
