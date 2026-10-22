---
title: Storage for any type
summary: "std::any can hold any copy-constructible value and remembers its type. This page covers the decay and copyability requirements on storing, the forms of any_cast and how they fail, the exception guarantees of assignment, the restriction on the small-object optimization, and the libc++ implementation."
updated: 2026-10-19
---

!!! tldr
    - `std::any` can hold any copy-constructible value and remembers its type; to get the value out you must name the exact type with `any_cast`, and `any_cast<long>` cannot retrieve an `int`.
    - The stored type is `decay_t<T>`: a string literal is stored as `const char*`, an array as a pointer, and `any` cannot hold references.
    - Move-only types (such as `unique_ptr`) cannot be put into an `any`, because `any` itself must be copyable, and copying it copies the contained value.
    - The reference forms of `any_cast` throw `bad_any_cast` on a type mismatch; the pointer forms return `nullptr`.
    - The standard recommends that small objects not be dynamically allocated, but this optimization may only be applied to types whose move constructor does not throw; otherwise `any`'s move and `swap` could not be `noexcept`.

## What any is

```cpp run title="any-cast.cpp" ok
#include <any>
#include <cassert>
#include <string>

int main() {
  std::any x = 5;                       // holds an int
  assert(std::any_cast<int>(x) == 5);   // get a copy
  std::any_cast<int&>(x) = 10;          // get a reference, modify in place
  assert(std::any_cast<int>(x) == 10);

  try {
    (void)std::any_cast<long>(x);       // int ≠ long
    assert(false);
  } catch (const std::bad_any_cast&) {}

  assert(std::any_cast<long>(&x) == nullptr);  // the pointer form does not throw

  x = "Meow";                           // stores a const char*
  assert(x.type() == typeid(const char*));

  x.reset();
  assert(!x.has_value() && x.type() == typeid(void));
}
```

`std::any` is a container that can hold a value of any copyable type and remembers what type that value is. Note 1 in [any.general] explains the design intent: it can hold values of different types but does not convert between them; `5` is strictly an `int`, and becomes neither `"5"` nor `5.0`. Whatever type went in is the type you must write to get it out.

`any` is a classic example of **type erasure** ([[g:type-erasure]]): the type `any` itself does not carry the contained value's type, and operations such as copying, destroying and retrieving by type are performed at run time through indirect calls. `std::function` ([[func.wrap.func]]) uses the same technique.

It and [[variant]] can both hold values of different types, but they make opposite trade-offs:

| | `variant<Ts...>` | `any` |
|---|---|---|
| Which types can be stored | the `Ts...` fixed at compile time | any copy-constructible object type |
| Storage | inside the object; heap allocation not allowed | may be heap-allocated; small objects preferably in an internal buffer |
| Access | `get`, `visit`; the compiler can check exhaustiveness | `any_cast`; you must name the exact type |
| Type information | a compile-time index | a run-time `type_info` |

¶1 [any.class.general] calls whether an `any` has a value, and what value if so, its **state**; the stored instance is called the **contained value**. Two states are equivalent if either both have no value, or both have a value and the contained values are equivalent.

## Storing: decay and copyability

### Converting construction

¶5 The converting constructor `template<class T> any(T&& value)` in [any.cons] first lets `VT` be `decay_t<T>`, and what is stored is an object of type `VT` direct-initialized with `std::forward<T>(value)` (paragraph 8). `decay_t` has several consequences:

- `any a = "Meow";` stores a `const char*`, not a `const char[5]`;
- arrays become pointers, and functions become function pointers;
- what is stored is always a non-reference, non-cv object type; `any` cannot hold references.

¶6 The constraints are that `VT` is not `any`, is not a specialization of `in_place_type_t`, and `is_copy_constructible_v<VT>` is true. ¶7 The precondition is that `VT` meets *Cpp17CopyConstructible* ([[utility.arg.requirements]]). These two levels of requirement belong to different specification elements ([[structure.specifications]]):

| Element | Content | When not satisfied |
|---|---|---|
| *Constraints* | syntactically copy-constructible | the constructor does not participate in overload resolution; `is_constructible_v<any, VT>` is false |
| *Preconditions* | semantically, copying yields an equivalent value and does not modify the source | undefined behavior |

So putting a `unique_ptr` into an `any` is a compile error with no viable conversion: the constructor simply disappears from the overload set, rather than triggering some `static_assert`:

```cpp run title="any-move-only.cpp" error
#include <any>
#include <memory>

std::any a = std::make_unique<int>(1);  // error: unique_ptr is not copyable
```

`in_place_type_t` is excluded so that a call like `any(std::in_place_type<int>)` goes to the `in_place` constructor below instead of storing the tag object itself. The converting constructor is not `explicit`, so any copyable value can implicitly become an `any`, which is a trap when `any` is a function parameter (see Common misconceptions).

### In-place construction and make_any

¶10 `explicit any(in_place_type_t<T>, Args&&...)` direct-non-list-initializes a `VT` with `args...`, constrained on `VT` being copy-constructible and constructible from `Args...`. ¶16 There is also a version that begins with an `initializer_list<U>`. They suit types that need several constructor arguments, or types that can be copied but not moved, without constructing a temporary first and moving it in.

[any.nonmembers]/2 `make_any<T>(args...)` is equivalent to `any(in_place_type<T>, std::forward<Args>(args)...)`, and paragraph 3 is the `initializer_list` version. The advantage of `make_any` is that you can write `std::make_any<std::vector<int>>({1, 2, 3})`: `T` is given explicitly and the `U` in `initializer_list<U>` is deduced.

[any.modifiers]/4 `emplace<T>(args...)` first calls `reset()`, then constructs in place and returns a reference to the new value; its constraints are the same as for `in_place` construction.

```cpp run title="any-construct.cpp" ok
#include <any>
#include <cassert>
#include <complex>
#include <type_traits>
#include <vector>

struct Throws { Throws() { throw 1; } };

int main() {
  auto a = std::make_any<std::complex<double>>(1.0, 2.0);
  auto b = std::make_any<std::vector<int>>({1, 2, 3});
  assert(std::any_cast<std::vector<int>&>(b).size() == 3);

  std::any c(std::in_place_type<std::vector<int>>, 5, 42);
  assert(std::any_cast<const std::vector<int>&>(c)[4] == 42);

  auto& v = c.emplace<std::vector<int>>(2u, 7);  // returns a reference to the new value
  v.push_back(8);
  assert(std::any_cast<std::vector<int>&>(c).size() == 3);

  try { a.emplace<Throws>(); } catch (int) {}
  assert(!a.has_value());  // after construction throws, the any is definitely empty

  static_assert(std::is_nothrow_move_constructible_v<std::any>);
}
```

### Why it must be copyable

`any` itself is a copyable type, and `any b = a;` must work. Once the type is erased, copying an `any` can only call a copy function recorded when the value was stored, and that function has to be instantiated at the moment of storing. If storing a `unique_ptr` were allowed, only two options would remain:

1. Discover at run time, when copying the `any`, that the contained value is not copyable, and throw. An error that could be found at compile time is postponed to run time, and the type property "`any` is copyable" becomes untrustworthy.
2. Make `any` itself non-copyable. Then it could not be copied and passed by value like an ordinary value, which defeats its purpose.

The standard chose to reject at the entrance: converting construction, `in_place` construction, converting assignment and `emplace` all carry the constraint `is_copy_constructible_v<VT>`. `std::function` requires its callable to be copyable for the same reason; that restriction later gave rise to the move-only `std::move_only_function` (C++23, [[func.wrap.move]]), whereas `any` still has no standard move-only version. When you need to store a move-only object, a common approach is to wrap it in a `std::shared_ptr<T>`, so that what is copied is shared ownership.

## Retrieving: any_cast

### Reference forms

[any.nonmembers]/4 The three overloads that take an `any` by reference are:

```cpp
template<class T> T any_cast(const any& operand);
template<class T> T any_cast(any& operand);
template<class T> T any_cast(any&& operand);
```

Let `U` be `remove_cvref_t<T>`. ¶6 They return `static_cast<T>(*any_cast<U>(&operand))`, with the third overload applying `std::move` before the conversion; that is, they call the pointer form internally and dereference. ¶7 If `operand.type() != typeid(remove_reference_t<T>)`, they throw `bad_any_cast`.

`T` determines how the value is retrieved: `any_cast<int>` copies out an `int`; `any_cast<int&>` returns an lvalue reference to the contained value, which can be modified in place; `any_cast<const int&>` returns a read-only reference; `any_cast<std::string&&>(std::move(a))` hands over the contained value as an rvalue, so it can be moved out.

¶5 There is also a *Mandates*: the three overloads require `is_constructible_v<T, const U&>`, `is_constructible_v<T, U&>` and `is_constructible_v<T, U>` respectively. This is a const-correctness check: you cannot get a `U&` out of a `const any&`, nor a `U&&` out of an lvalue `any&`. It is *Mandates* rather than *Constraints*: the three overloads are distinguished by the value category of `operand`, so a wrong `T` does not let another overload step in; it is simply an error.

<div class="compare" markdown="1">

```cpp error
#include <any>
#include <string>
int main() {
  const std::any y = std::string("cat");
  // any_cast cannot cast away const
  std::any_cast<std::string&>(y);  // error
}
```

```cpp error
#include <any>
int main() {
  std::any a = 1;
  // pointer form: T cannot be void
  return std::any_cast<void>(&a)
         != nullptr;  // error
}
```

</div>

The run-time check uses `typeid(remove_reference_t<T>)`. `typeid` ignores top-level cv ([[expr.typeid]]), so `any_cast<const int&>` can retrieve an `int`. When there is no value, `type()` is `typeid(void)`, which is unequal to every object type, so `bad_any_cast` is thrown as well.

```cpp run title="any-move-out.cpp" ok
#include <any>
#include <cassert>
#include <string>

int main() {
  std::any x = std::string("Meow");
  std::string s = std::any_cast<std::string&&>(std::move(x));
  assert(s == "Meow");
  assert(x.has_value());  // the moved-from string is still in the any
}
```

After moving out, the `any` still contains a `string` in a valid but unspecified state; the `any` itself has not become empty.

### Pointer forms

[any.nonmembers]/9 The two overloads that take an `any` by pointer:

```cpp
template<class T> const T* any_cast(const any* operand) noexcept;
template<class T> T* any_cast(any* operand) noexcept;
```

`T` cannot be `void` (*Mandates*). ¶10 If `operand` is non-null and `operand->type() == typeid(T)`, it returns a pointer to the contained value, otherwise `nullptr`. The standard's Example 2 uses it to test the type: `any_cast<string>(&operand) != nullptr`.

The pointer forms never throw: a null pointer, no value and a type mismatch are all reported with `nullptr`. This mirrors the two failure modes of `dynamic_cast` (the pointer form gives `nullptr`, the reference form throws `bad_cast`), and corresponds to variant's `get_if` and `get`.

### bad_any_cast

`bad_any_cast` in [any.bad.any.cast] publicly inherits from `bad_cast`, not directly from `exception`. It belongs to the same family as the `bad_cast` thrown when a reference `dynamic_cast` fails; both indicate a failed run-time type check, and `catch (const std::bad_cast&)` catches both.

## Observers and reset

[any.observers]/1 `has_value()` returns `true` when there is a contained value. Paragraph 2: `type()` returns `typeid(T)` when there is a value and `typeid(void)` when there is not.

`type()` depends on RTTI. Under `-fno-rtti`, libc++ does not provide `type()`, but `any_cast` still works: it uses the address of a per-type static variable as the type identifier instead.

[any.modifiers]/17 `reset()` destroys the contained value (if any), after which `has_value()` is false. The destructor has the effect of `reset()` ([any.cons]/22).

## Exception guarantees of copy, move and assignment

[any.cons]/2 When the source has a value, copy construction is equivalent to `any(in_place_type<T>, any_cast<const T&>(other))`; it may allocate memory and may throw whatever `T`'s copy constructor throws.

¶4 Move construction is `noexcept`. When the source has a value, the new object either takes over the source's contained value directly, or contains an object of the same type move-constructed from that value (as an rvalue). These two phrasings correspond to the cases where the value is on the heap and in the internal buffer, respectively. The standard does not specify the state of the source after the move: it may be empty, or it may still have a moved-from value. libc++ empties the source in both cases, but portable code cannot rely on that.

The three assignments in [any.assign] all construct first and then swap:

| Operation | Effect | Exception guarantee |
|---|---|---|
| `operator=(const any& rhs)` (¶1–3) | as if by `any(rhs).swap(*this)` | no effect if an exception is thrown |
| `operator=(any&& rhs) noexcept` (¶4–6) | as if by `any(std::move(rhs)).swap(*this)` | the state of `*this` is equivalent to the original state of `rhs` |
| `template<class T> operator=(T&& rhs)` (¶7–12) | constructs a temporary `any` holding a `VT`, then swaps it with `*this` | no effect if an exception is thrown |

The new value is fully constructed in a temporary object first and then exchanged with a non-throwing `swap`. This contrasts with variant's assignment: variant cannot allocate on the heap, constructing a temporary first requires extra conditions, and so it may lose its value; `any` can always construct a temporary on the heap, so assignment always has the strong exception guarantee.

`emplace` is the opposite. [any.modifiers]/8 specifies that if the constructor throws, `*this` does not contain a value, and the original contained value has already been destroyed. This is a definite outcome, unlike `variant::emplace`, which merely may hold no value. Giving up the strong guarantee buys in-place construction without a temporary object.

## Small-object optimization

[any.class.general]/3 is the paragraph with the most engineering significance in the whole subclause:

!!! std
    Implementations should avoid the use of dynamically allocated memory for a small contained value. However, any such small-object optimization shall only be applied to types `T` for which `is_nothrow_move_constructible_v<T>` is `true`.

The first sentence uses "should", so it is only a recommendation: the standard does not define how small is small, and an implementation that does no **small-object optimization** at all ([[g:small-object-optimization]], placing small values directly in a buffer inside the object) also conforms. The second sentence uses "shall", a hard requirement: a type whose move constructor may throw must not be placed in the internal buffer, however small it is.

The reason for the second sentence is that `any`'s move constructor, move assignment and `swap` are all `noexcept`. When the value is on the heap, moving an `any` merely transfers a pointer and cannot throw; when the value is in the internal buffer, moving an `any` must actually move-construct a `T`, and if that step can throw, the `noexcept` cannot be honored. So types whose move may throw can only go on the heap. The standard's Example 1 says that an `int` can be placed in the internal buffer.

These cases can be observed directly on libc++:

```cpp run title="any-sbo.cpp" ok
#include <any>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Small { void* p[3]; };  // 24 bytes, move does not throw
struct Big { void* p[4]; };    // 32 bytes
struct Throwing {              // 1 byte, but move may throw
  Throwing() = default;
  Throwing(const Throwing&) {}
  Throwing(Throwing&&) noexcept(false) {}
};

template<class T>
int count() {
  int before = allocs;
  std::any a = T{};
  return allocs - before;
}

int main() {
  std::printf("sizeof(any)=%zu\n", sizeof(std::any));
  std::printf("int:%d Small:%d Big:%d Throwing:%d\n",
              count<int>(), count<Small>(), count<Big>(), count<Throwing>());
}
```

In our tests (arm64 macOS, libc++ 23) the output is `sizeof(any)=32` and `int:0 Small:0 Big:1 Throwing:1`. `Throwing` is only 1 byte but has to be heap-allocated because its move constructor is not `noexcept`. The buffer size is an implementation detail and differs between libstdc++ and MSVC; do not rely on it.

## The libc++ implementation

The following is based on libc++ 23's `<any>` as used in our tests.

`any` consists of a function pointer and a block of union storage:

```cpp
// simplified from libc++ <any>
class any {
  using _HandleFuncPtr = void* (*)(_Action, any const*, any*,
                                   const type_info*, const void*);
  union _Storage {
    void* __ptr;                                   // large object: points to the heap
    alignas(void*) char __buf[3 * sizeof(void*)];  // small object: stored in place
  };
  _HandleFuncPtr __h_ = nullptr;                   // nullptr means no value
  _Storage __s_;
};
```

On 64-bit platforms `sizeof(any) == 32`, and `has_value()` is just `__h_ != nullptr`.

A type can go into the buffer only if it meets three conditions at once: `sizeof(T) <= 3 * sizeof(void*)`, `alignof(T) <= alignof(void*)` and `is_nothrow_move_constructible_v<T>`. The third condition is the "shall" of [any.class.general]/3.

Each type `T` corresponds to a static function of `_SmallHandler<T>` or `_LargeHandler<T>`, which dispatches operations on an enumeration (destroy, copy, move, get, get type info). This amounts to a hand-written vtable with a single entry: each `any` stores just one extra function pointer, instead of a vtable pointer plus a polymorphic object on the heap.

When moving, a large object just copies `__ptr` to the target and sets the source's `__h_` to null, corresponding to the direct takeover in [any.cons]/4; a small object move-constructs a `T` in the target buffer and then destroys the source, corresponding to constructing an object of the same type from an rvalue. In both cases the source becomes empty.

When `any_cast` compares types, it compares `type_info` if RTTI is available, and otherwise compares the addresses of per-type static variables. For a function type `T`, the pointer form of `any_cast` returns `nullptr` directly, because `any` can only store function pointers, never functions. Construction of large objects allocates memory first and frees it if construction throws, so nothing leaks.

## Common misconceptions

!!! pitfall "Taking any as a parameter postpones type checking to run time"
    `void set(std::string key, std::any value);` accepts anything copyable. `set("timeout", 30)` stores an `int`, and a reader writing `any_cast<long>` gets `bad_any_cast`; `set("name", "bob")` stores a `const char*`, not a `std::string`, so `any_cast<std::string>` fails as well. The writer and the reader must agree on the exact type, usually with `in_place_type` or explicit construction (`std::string("bob")`).

!!! pitfall "Thinking any can hold references or arrays"
    `decay_t` turns arrays into pointers and functions into function pointers, and removes references and cv. `int arr[3]; std::any a = arr;` stores an `int*`, a potentially dangling pointer, not a copy of three `int`s.

!!! pitfall "Relying on a moved-from any being empty"
    [any.cons]/4 does not specify what state a moved-from `any` is in. libc++ empties it, but the standard allows it to still hold a moved-from value. When you need the empty state, call `reset()` explicitly.

## Questions

!!! question "Question 1"
    After `std::any a = 1;`, what are the results of `std::any_cast<int&&>(a)` and `std::any_cast<const int&&>(std::as_const(a))`?

<details markdown="1">
<summary>Answer</summary>

Both are compile errors. The first: `a` is a non-const lvalue, so `any_cast(any&)` is selected, and its *Mandates* requires `is_constructible_v<int&&, int&>`; an rvalue reference cannot bind to an lvalue, so it is false. To get an rvalue you must write `any_cast<int&&>(std::move(a))`, which selects the third overload and requires `is_constructible_v<int&&, int>`, which is true.

The second selects `any_cast(const any&)` and requires `is_constructible_v<const int&&, const int&>`, again an rvalue reference binding to an lvalue, so it is false. The second type in the *Mandates* (`const U&`, `U&`, `U`) describes what value category can be obtained from this `any`; `T` can only add const on top of that or make a copy, and cannot conjure up an rvalue.
</details>

!!! question "Question 2"
    Does an implementation that does no small-object optimization at all, heap-allocating every value, conform to the standard? What about an implementation that uses the internal buffer for every type with `sizeof(T) <= 16`?

<details markdown="1">
<summary>Answer</summary>

The former conforms: the first sentence of [any.class.general]/3 says "should", which is only a recommendation. The latter does not: the second sentence says "shall", and a type for which `is_nothrow_move_constructible_v<T>` is false must not be placed in the internal buffer, however small. Once this is violated, `any(any&&) noexcept` and `swap` cannot be implemented correctly: moving the `any` requires move-constructing `T`, and if `T` throws, the only option is to call `std::terminate`.
</details>

## Summary

| Operation | Key points |
|---|---|
| storing (converting construction, `in_place`, converting assignment, `emplace`) | stores `decay_t<T>`; constraints require copy-constructibility; preconditions require *Cpp17CopyConstructible* |
| small-object optimization | should avoid dynamic allocation for small objects; shall only be applied to types whose move does not throw |
| copy construction, copy assignment | may throw; assignment constructs then swaps, with the strong exception guarantee |
| move construction, move assignment, `swap`, `reset` | `noexcept`; the state of a moved-from `any` is unspecified |
| `emplace` | `reset()` first, then construct; if construction throws, `*this` is definitely empty |
| `type()` | `typeid(T)` with a value, `typeid(void)` without |
| reference forms such as `any_cast<T>(any&)` | *Mandates* checks const correctness; a type mismatch throws `bad_any_cast` |
| pointer form `any_cast<T>(any*)` | `T` cannot be `void`; returns `nullptr` on a type mismatch or a null pointer |
| `make_any<T>(args...)` | equivalent to `any(in_place_type<T>, args...)` |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[any.general]/1 just says that the components described in this subclause are for operating on objects of a **discriminated type** ([[g:discriminated-type]]), that is, a type that can hold values of different types and remembers which.

[any.synop] is the header synopsis: `<any>` includes `<initializer_list>` and `<typeinfo>`, and declares `bad_any_cast`, `any`, the non-member `swap`, two `make_any`s, and three reference forms and two pointer forms of `any_cast`. Only `any`'s default constructor is `constexpr`, so `constinit std::any g;` works.

[any.bad.any.cast]/2: `bad_any_cast::what()` returns an implementation-defined NTBS.

[any.class.general]/2: the non-member `any_cast` functions provide type-safe access to the contained value.

In [any.cons] and [any.modifiers], the `initializer_list` versions (¶16–21, ¶9–16) are the same as the corresponding ordinary versions with an extra `initializer_list<U>&` argument; the postcondition in ¶20 only says that `*this` contains a value. The constraints on converting assignment ([any.assign]/8) do not exclude `in_place_type_t`, because assignment does not need a tag for disambiguation.

[any.modifiers]/19 `swap` exchanges the states of the two; [any.nonmembers]/1 the non-member `swap(x, y)` is equivalent to `x.swap(y)`. The note in [any.observers]/3 says `type()` can be used to compare against types known at compile time or only at run time.

</details>
