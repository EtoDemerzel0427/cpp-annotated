---
title: Initializer lists
summary: "std::initializer_list<E> is a lightweight view of an array of const E that the compiler creates during list-initialization; this subclause specifies its interface, while its creation and the lifetime of the backing array are specified by the core language."
updated: 2026-10-19
---

!!! tldr
    - `std::initializer_list<E>` is a view of an array of `const E`; copying it doesn't copy the elements.
    - The elements are read-only and can't be moved from, so `vector<unique_ptr<int>> v{...}` doesn't compile.
    - The lifetime of the backing array is decided by the core language; returning an `initializer_list` from a function leaves a dangling pointer.
    - A program may not specialize `initializer_list`; doing so is ill-formed.
    - For an empty list `begin()` equals `end()`, but the value is unspecified; to check for emptiness use `empty()` or `size()`.

## What the compiler does for you

When you write `std::vector<int> v{1, 2, 3};`, the compiler does two things ([[dcl.init.list]]):

1. It creates a **backing array** ([[g:backing-array]]) of type `const int[3]` and copy-initializes its elements from `1, 2, 3` one by one;
2. It constructs a `std::initializer_list<int>` object referring to that array and passes it to `vector`'s **initializer-list constructor** ([[g:initializer-list-constructor]]), that is, a constructor whose first parameter is `std::initializer_list<E>`.

`initializer_list` has no public constructor that can take elements; only the compiler can create a non-empty list, during list-initialization. Its priority in overload resolution and the lifetime of the backing array are specified by the core language; this subclause specifies only its library interface.

¶1 [support.initlist.general] `<initializer_list>` defines this class template. All functions in this subclause are signal-safe ([[support.signal]]) and can be called in a signal handler.

## Interface [initializer.list.syn]

```cpp
// all freestanding
namespace std {
  template<class E> class initializer_list {
  public:
    using value_type      = E;
    using reference       = const E&;
    using const_reference = const E&;
    using size_type       = size_t;
    using iterator        = const E*;
    using const_iterator  = const E*;

    constexpr initializer_list() noexcept;

    constexpr const E* data() const noexcept;
    constexpr size_t size() const noexcept;
    constexpr bool empty() const noexcept;
    constexpr const E* begin() const noexcept;
    constexpr const E* end() const noexcept;
  };
}
```

Both `reference` and `iterator` are const: elements can only be read through an `initializer_list`.

### It is a view (¶1)

!!! std
    An object of type `initializer_list<E>` provides access to an array of objects of type `const E`.

¶1 An object of type `initializer_list<E>` provides access to an array of objects of type `const E`. Note 1 says a pair of pointers or a pointer plus a length would be obvious representations, and copying an `initializer_list` doesn't copy the underlying elements. Like `std::span<const E>`, it doesn't own its elements.

```cpp run title="initlist-ok.cpp" ok
#include <initializer_list>

int sum(std::initializer_list<int> il) {
  int s = 0;
  for (int x : il) s += x;
  return s;
}

int main() {
  std::initializer_list<int> il = {1, 2, 3};  // the array's lifetime is extended to that of il
  auto copy = il;                             // shallow copy: both refer to the same array
  return (sum({4, 5, 6}) == 15 && copy.begin() == il.begin()) ? 0 : 1;
}
```

This has two consequences.

First, elements can't be moved. The elements of the backing array are `const E`, so `std::move(*il.begin())` has type `const E&&`, which can only match the copy constructor. So a container's initializer-list constructor can only copy elements, and the following code doesn't compile, because `unique_ptr` isn't copyable:

```cpp run error
#include <memory>
#include <vector>
std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};  // error: requires copying unique_ptr
```

Even when the elements are copyable, every element of a container initialized with `{...}` is copied from the backing array rather than constructed directly from its initializer.

Second, the array's lifetime isn't its business. [[dcl.init.list#6]] says the backing array is like any other temporary object ([[class.temporary]]), except that when it is used to initialize an `initializer_list` object, its lifetime is extended as if a reference were bound to a temporary, up to the lifetime of that object. An `initializer_list` copied out afterwards doesn't extend it further:

```cpp run title="initlist-dangling.cpp" ub
#include <initializer_list>

std::initializer_list<int> make() {
  return {1, 2, 3};      // the array is destroyed when make returns
}

int main() {
  auto il = make();
  return *il.begin();    // UB: reads an array that has been destroyed
}
```

Clang 23 gives a `-Wreturn-stack-address` warning for `return {1, 2, 3};`.

### No specializations (¶2)

¶2 If a program declares an explicit or partial specialization of `initializer_list`, it is ill-formed.

The general rule ([[namespace.std]]) allows programs to specialize some standard library class templates for their own types; this is stricter. The reason is that the compiler constructs `initializer_list` objects directly, filling in the array's address and length. If a user specialized `initializer_list<MyType>`, the compiler wouldn't know how to construct it.

```cpp run error
#include <initializer_list>
struct S {};
template<> class std::initializer_list<S> {};   // error: may not be specialized
```

!!! impl
    libc++ gives this class template Clang's `[[clang::no_specializations]]` attribute, so the specialization above is rejected with the diagnostic `'initializer_list' cannot be specialized`. libc++'s data members are `const E* __begin_` and `size_t __size_`, and there is also a private `(const E*, size_t)` constructor that the compiler calls and users can't.

## Construction and access [support.initlist.cons] [support.initlist.access]

| Member | Specification |
|---|---|
| `initializer_list()` | Postcondition: `size() == 0` (cons ¶1) |
| `begin()` | Points to the start of the array; if `size() == 0`, the values of `begin()` and `end()` are unspecified but must be identical (access ¶1) |
| `end()` | `begin() + size()` (¶2) |
| `data()` | `begin()` (¶3) |
| `size()` | The number of elements in the array (¶4), constant complexity (¶5) |
| `empty()` | `size() == 0` (¶6) |

An empty list's `begin()` isn't guaranteed to be a null pointer, only to equal `end()`. libc++'s default constructor sets it to `nullptr`, but code shouldn't rely on that; to check for emptiness, use `empty()` or `size()`.

!!! note "`data()` and `empty()`"
    These two members were newly added in a working draft after C++23, and the feature-test macro `__cpp_lib_initializer_list` is `202511L` ([[version.syn]]). At the same time, the non-member `std::begin(initializer_list<E>)` and `std::end(initializer_list<E>)` in `<initializer_list>` were removed from the synopsis; the general `std::begin(c)` and `std::end(c)` in `<iterator>` call the member functions and apply just as well ([[iterator.range]]). At the time of writing, libc++ doesn't have `data()` or `empty()` yet, doesn't define this macro, and still keeps the non-member `begin` and `end`.

## Interaction with the core language

- **Overload resolution** ([[over.match.list]]): when a class has initializer-list constructors, a non-empty `{...}` considers them first. So `std::vector<int> v{10, 1};` has two elements, and `std::vector<int> v(10, 1);` has ten 1s.
- **`auto` deduction** ([[dcl.spec.auto]]): `auto x = {1, 2};` deduces `std::initializer_list<int>`; since C++17, `auto x{1};` deduces `int`, and `auto x{1, 2};` is ill-formed. Template argument deduction doesn't deduce `initializer_list<T>` from `{...}` unless the parameter itself is written as `std::initializer_list<T>` ([[temp.deduct.call]]).
- **Range-based for** ([[stmt.ranged]]): `for (int x : {1, 2, 3})` is valid; the range is deduced as `initializer_list<int>`, and the array's lifetime is extended across the whole loop.
- **It must be declared first**: when `std::initializer_list` is used (including implicit uses that don't write the type name, such as `auto x = {1, 2};`) and its declaration isn't reachable, the program is ill-formed ([[dcl.init.list#2]]). In practice this means you must first `#include <initializer_list>` or some header that includes it.

!!! history
    `initializer_list` was introduced in C++11 along with list-initialization ([[N2672]]), and C++14 made its members `constexpr`. Since C++26, the backing array is a potentially non-unique object ([[dcl.init.list]] Note 6, [[intro.object]]), so an array with constant contents can be placed in static read-only storage and shared by multiple evaluations ([[P2752R3]]).
