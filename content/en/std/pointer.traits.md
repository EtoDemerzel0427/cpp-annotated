---
title: Pointer traits and to_address
summary: "pointer_traits gives raw pointers and fancy pointers a uniform interface: how element_type, difference_type and rebind are derived from the template arguments, pointer_to and the optional to_address; std::to_address turns any pointer-like object back into a raw pointer without dereferencing it."
updated: 2026-10-19
---

!!! tldr
    - `pointer_traits<P>` answers what a pointer-like type points to (`element_type`), what subtracting two of them yields (`difference_type`), and what the same kind of pointer to another type is (`rebind<U>`).
    - When the type does not declare these members itself, `pointer_traits` by default takes the first template type argument as `element_type`, and `rebind` replaces that argument.
    - A type whose `element_type` cannot be deduced gets an empty `pointer_traits`, not a hard error, so it can be used safely in a `requires` expression.
    - `std::to_address(p)` gets a raw pointer through `operator->` or `pointer_traits::to_address` without dereferencing, so it works on `end()` iterators too.

## Fancy pointers

C++ allocators allow `allocator::pointer` to be a class type rather than `T*`; this is called a **fancy pointer** ([[g:fancy-pointer]]). The typical example is an offset pointer in shared memory: the same shared memory segment is mapped at different addresses in different processes, so storing an absolute address is meaningless, and only an offset relative to the pointer itself works. Boost.Interprocess's `offset_ptr` is such a pointer.

For a container to stay generic over such pointers, it has to answer several questions: what type does it point to? What type does subtracting two pointers yield? How do I get the same kind of pointer, but pointing to `Node`? How do I get a fancy pointer to an object from a reference to it? `pointer_traits` answers all of these uniformly, and [[allocator.traits]] also builds on it to derive `const_pointer`, `void_pointer` and `difference_type`.

```cpp run title="pointer-traits.cpp" ok
#include <cassert>
#include <memory>
#include <type_traits>
#include <vector>

template<class T, class Tag = void>
struct Ptr {                       // a minimal fancy pointer
    T* raw = nullptr;
    T& operator*() const { return *raw; }
    T* operator->() const { return raw; }
    static Ptr pointer_to(T& r) { return Ptr{&r}; }
};

using PT = std::pointer_traits<Ptr<int, char>>;
static_assert(std::is_same_v<PT::element_type, int>);               // the first template argument
static_assert(std::is_same_v<PT::difference_type, std::ptrdiff_t>);  // the default
static_assert(std::is_same_v<PT::rebind<long>, Ptr<long, char>>);   // replaces the first template argument

// a type that is not pointer-like gets an empty pointer_traits
template<class P> concept has_elem = requires { typename std::pointer_traits<P>::element_type; };
static_assert(!has_elem<int>);
static_assert(has_elem<int*>);

int main() {
    int x = 42;
    Ptr<int, char> p = PT::pointer_to(x);
    assert(std::to_address(p) == &x);                  // falls back to p.operator->()
    std::vector<int> v{1, 2, 3};
    assert(std::to_address(v.begin()) == v.data());     // iterators work too
    assert(std::to_address(v.end()) == v.data() + 3);   // no dereference, so end() is safe
}
```

`Ptr` declares no member types, yet `pointer_traits` still derives every answer. The rules follow one by one.

## General [pointer.traits.general]

¶1 `pointer_traits` provides a uniform interface to certain attributes of pointer-like types.

Raw pointers `T*` have a ready-made partial specialization: `pointer` is `T*`, `element_type` is `T`, `difference_type` is `ptrdiff_t`, `rebind<U>` is `U*`, and `pointer_to(r)` returns `addressof(r)`. The members of the primary template have to be derived from `Ptr`.

## How the member types are derived [pointer.traits.types]

### If deduction fails, the whole specialization is empty (¶1–¶2)

¶1 defines the exposition-only class template *ptr-traits-elem* and the concept *has-elem-type*. ¶2 specifies that a specialization generated from the primary template has the members below only if `Ptr` satisfies *has-elem-type*; otherwise it has none of them.

This was established by [[LWG3545]]. Before that, `pointer_traits<int>` was a hard error on instantiation, and any code detecting whether a type is pointer-like would fail to compile because of it. Now `pointer_traits<int>` is just an empty class, so `has_elem<int>` in the example above truthfully yields `false`.

### `element_type` (¶4)

`element_type` is *ptr-traits-elem*`<Ptr>::type`, determined in this order:

1. `Ptr::element_type` if it exists;
2. otherwise, if `Ptr` is a class template specialization of the form `SomePointer<T, Args...>`, the first template argument `T`;
3. otherwise it cannot be deduced, and *has-elem-type* is not satisfied.

Rule 2 is a convention: it assumes that the first type argument of a fancy pointer is the pointed-to type, which holds for `offset_ptr<T, ...>` and for `Ptr<T, Tag>` in the example. It only applies to templates whose parameters are all types. `Args` in `SomePointer<T, Args...>` is a type pack, so a template with a non-type template parameter (such as `my_ptr<T, 16>`) does not match and has to declare `element_type` itself.

### `difference_type` (¶5) and `rebind` (¶6)

- ¶5 `difference_type`: `Ptr::difference_type` if that is valid and denotes a type; otherwise `ptrdiff_t`.
- ¶6 `rebind<U>`: `Ptr::rebind<U>` if that is valid and denotes a type; otherwise, if `Ptr` is `SomePointer<T, Args...>`, `SomePointer<U, Args...>`; otherwise instantiating `rebind` is {{ill-formed}}.

"Valid and denotes a type" is judged by the rules of template argument deduction ([[temp.deduct]]), so even if `Ptr::difference_type` is a private member or not a type, the result just falls back to the default with no error.

```cpp title="rebind-fail.cpp" error
#include <memory>
struct NotTemplate { using element_type = int; };            // not a template specialization, no rebind member
using R = std::pointer_traits<NotTemplate>::rebind<long>;   // error: instantiating rebind is ill-formed
```

libc++ reports it with a `static_assert`: Cannot rebind pointer; did you forget to add a rebind member to your pointer?

## `pointer_to` [pointer.traits.functions]

`pointer_to(r)` gets a pointer to an object from a reference to it. A common use in container implementations: you hold a reference to a node object (such as a sentinel node that is a member of the container) and need its fancy pointer form to store in the list.

- ¶1 *Mandates*: for the primary template, `Ptr::pointer_to(r)` is well-formed. `pointer_traits` does not synthesize it for you.
- ¶2 *Preconditions*: the pointer returned by `Ptr::pointer_to(r)` really points to `r` and can be used to access it.
- ¶3 The primary template returns `Ptr::pointer_to(r)`; the raw pointer version returns `addressof(r)`, not `&r` (see `addressof` in [[memory]]).
- ¶4 If `element_type` is cv `void`, the type of the parameter `r` is unspecified; otherwise it is `element_type&`. `void` has no reference type, so there is no portable way to call `pointer_traits<void*>::pointer_to`.

[[LWG3454]] made `pointer_to` `constexpr`.

## Optional member `to_address` [pointer.traits.optmem]

¶1 A specialization of `pointer_traits` may define a static member `to_address(pointer p)` to customize the library's behavior; specializations generated from the primary template have no such member. ¶2 It returns an `element_type*` pointing to the same location as `p`. The note in ¶3 says it is the inverse of `pointer_to` and, if defined, is used by the non-member `std::to_address`.

## `std::to_address` [pointer.conversion]

The most direct way to turn any pointer-like object back into a raw pointer is `&*p`. It has two problems: dereferencing an `end()` iterator or a null fancy pointer is undefined behavior, and `operator*` and `operator&` may both be overloaded to mean something else. C++20's `std::to_address` ([[P0653R2]]) gets the address without dereferencing:

- ¶1–¶2 For a raw pointer `T*`, it returns `p` directly; the *Mandates* requires `T` not to be a function type, so `to_address(&f)` is {{ill-formed}}.
- ¶3 For other types, it uses `pointer_traits<Ptr>::to_address(p)` if that is well-formed, and otherwise returns `to_address(p.operator->())`. This is a recursive call, so it is fine for `operator->` to return another fancy pointer.

Because it goes through `operator->` rather than `operator*`, `to_address(it)` gets the element address for any contiguous iterator of the standard library, including `end()`. The `contiguous_iterator` concept ([[iterator.concept.contiguous]]) uses exactly `to_address` to state the correspondence between iterators and element addresses.

!!! pitfall "to_address does not make an invalidated iterator valid"
    `to_address` itself does not dereference, but any operation on an iterator that has already been invalidated (including calling `operator->`) is still undefined behavior.

## Questions

!!! question "Question 1"
    `template<class T, int N> struct aligned_ptr { T* p; };` declares no member types. What is `pointer_traits<aligned_ptr<int, 16>>::element_type`?

<details markdown="1">
<summary>Answer</summary>

It does not exist. The second partial specialization of *ptr-traits-elem* requires the form `SomePointer<T, Args...>`, where `Args...` is a pack of type template arguments; the second template parameter of `aligned_ptr` is a non-type parameter, so matching fails. *has-elem-type* is then not satisfied, and by ¶2 the whole specialization has no members at all. The fix is to write `using element_type = T;` and `template<class U> using rebind = aligned_ptr<U, N>;` in `aligned_ptr`.
</details>

!!! question "Question 2"
    Why does `std::to_address` prefer `pointer_traits::to_address` over always using `operator->`?

<details markdown="1">
<summary>Answer</summary>

For some pointer-like types, `operator->` may be checked when the value is valid but not dereferenceable; for example, a debug-mode iterator asserts when `operator->` is called on `end()`. Some types have no `operator->` at all. Specializing `pointer_traits` with a `to_address` gives such a type a way to compute the address only, without any access checks. libc++ does exactly this: it specializes `pointer_traits` for `__bounded_iter`, its bounds-checked iterator in hardened mode, providing a `to_address` that does no bounds checking.
</details>

## Summary

| Member | Default source | When it cannot be derived |
|---|---|---|
| `element_type` | `Ptr::element_type`, otherwise the first template type argument | The whole specialization has no members |
| `difference_type` | `Ptr::difference_type`, otherwise `ptrdiff_t` | Never fails |
| `rebind<U>` | `Ptr::rebind<U>`, otherwise replace the first template argument | Instantiation is ill-formed |
| `pointer_to(r)` | Must be provided by `Ptr::pointer_to` | Ill-formed (*Mandates*) |
| `to_address(p)` | Optional, only an explicit specialization can provide it | `std::to_address` falls back to `operator->` |
