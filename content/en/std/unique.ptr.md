---
title: unique_ptr
summary: "The full rules of the exclusive-ownership pointer unique_ptr: deleters and the pointer type, incomplete types, the constraints on construction and assignment, the order of operations in reset, the conversion restrictions of the array version, the make_unique family, and the ABI cost of passing it by value."
updated: 2026-10-19
---

!!! tldr
    - `unique_ptr<T, D>` owns an object and disposes of it with deleter `D` when it is itself destroyed. The default deleter and stateless deleters take no space, so `unique_ptr` is the size of a plain pointer; a function pointer deleter makes it twice as big.
    - `T` may be an incomplete type, but wherever the `unique_ptr` is destroyed the complete `T` must be visible, or compilation fails. The pimpl idiom has to define the destructor in the `.cpp` file.
    - If the deleter defines a nested type `pointer`, that is the type `unique_ptr` stores, so it can manage handles that are not pointers, such as file descriptors.
    - `reset` stores the new pointer first and then calls the deleter; move assignment does `reset(u.release())` first and then assigns the deleter, so `head = std::move(head->next)` is undefined behavior.
    - `unique_ptr<T[]>` forbids conversion from arrays of derived classes; `make_unique<T[]>(n)` value-initializes the elements, `make_unique_for_overwrite` does not initialize them.

## Exclusive ownership [unique.ptr.general]

¶1–¶3 The standard first defines the abstraction of a **unique pointer** ([[g:unique-pointer]]): an object *u* stores a pointer to a second object *p* and disposes of *p* when *u* is itself destroyed; *u* is then said to own *p*. The mechanism used for disposal is called *p*'s **deleter** ([[g:deleter]]), a function object whose correct invocation disposes of *p* appropriately, typically by deleting it. *u* can, on request, reset its stored pointer and deleter, but must dispose of the old object with the old deleter before the replacement is considered complete.

¶4 Each specialization of `unique_ptr` implements these strict ownership semantics: it can be move-constructed and move-assigned but not copied. The template parameter `T` may be an incomplete type, under the conditions below. The note in ¶5 describes its uses: exception safety for dynamically allocated memory, passing ownership into a function, and returning ownership from a function.

## Deleters and the `pointer` type [unique.ptr.single.general]

### The deleter determines the size

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <memory>

struct FreeDeleter {
  void operator()(void* p) const noexcept { std::free(p); }
};

int main() {
  auto lam = [](int* p) { delete p; };
  using FP = void (*)(int*);
  std::printf("%zu\n", sizeof(std::unique_ptr<int>));                  // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter>));     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, decltype(lam)>));   // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FP>));              // 16
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter&>));    // 16
}
```

The comments show the output with 64-bit libc++ in our tests. Empty deleters (the default deleter, empty function objects, captureless lambdas) take no space, thanks to the empty base optimization or `[[no_unique_address]]` (potentially-overlapping subobjects in [[intro.object]]). The standard does not require this, but all mainstream implementations do it, so the verdict is {{impl}}.

A function pointer deleter has to store a pointer, which makes `unique_ptr` twice as big, and calls through a function pointer are hard to inline. So deleters should preferably be written as stateless function objects.

### Requirements on `T` and `D` (¶1–¶3)

¶1 If `T*` is not a valid type, instantiating the definition of `unique_ptr<T, D>` is ill-formed. Note 1 gives `unique_ptr<T&, D>` and `unique_ptr<int() const, D>` as examples ([[LWG4144]]).

¶2 `D` must be a function object type, an lvalue reference to a function, or an lvalue reference to a function object type; for a value `d` of `D` and a value `ptr` of `pointer`, `d(ptr)` must be valid and dispose of the pointer as appropriate. ¶3 If `D` is not a reference type, it must meet *Cpp17Destructible*.

When `D` is a reference type, `unique_ptr` stores only a reference; the deleter object is owned externally and must outlive the `unique_ptr`.

### `pointer` is not necessarily `T*` (¶4–¶5)

!!! std "[unique.ptr.single.general]/4"
    If the qualified-id `remove_reference_t<D>::pointer` is valid and denotes a type, then `unique_ptr<T, D>::pointer` shall be a synonym for `remove_reference_t<D>::pointer`. Otherwise `unique_ptr<T, D>::pointer` shall be a synonym for `element_type*`.

¶4 If the deleter has a nested type `pointer`, that is the type `unique_ptr` stores; otherwise it is `T*`. `pointer` must meet *Cpp17NullablePointer* ([[nullablepointer.requirements]]): comparable with `nullptr`, null when value-initialized, and copyable without throwing.

This lets `unique_ptr` manage handles that are not pointers, such as POSIX file descriptors or a Win32 `HANDLE`: wrap the handle in a type that meets *Cpp17NullablePointer* and write `using pointer = Handle;` in the deleter. The example in ¶5 shows that an allocator's fancy pointer type can also be used as `pointer`.

## The default deleter and incomplete types [unique.ptr.dltr]

```cpp run error
#include <memory>
class Widget {
  struct Impl;                   // incomplete type
  std::unique_ptr<Impl> impl;    // OK: T may be incomplete
public:
  Widget();
  // no destructor declared: the implicit destructor is defined where Impl is still incomplete
};
void use() { Widget w; }         // error: instantiates default_delete<Impl>::operator()
```

[unique.ptr.dltr.general] ¶2 allows the `T` of `default_delete<T>` to be incomplete. But [unique.ptr.dltr.dflt] ¶3 specifies that `default_delete<T>::operator()` requires `T` to be a complete type (*Mandates*), and by ¶4 its effect is to call `delete` on the pointer.

`Widget` declares no destructor, so the implicit destructor is defined where it is first used, where `Impl` is still incomplete. Destroying `impl` instantiates `default_delete<Impl>::operator()`, and compilation fails. libc++ (Clang 23) reports that `sizeof` was applied to the incomplete type `Widget::Impl`.

The correct way is to declare only `~Widget();` in the header and write `Widget::~Widget() = default;` in the `.cpp` file where `Impl` is complete. Move assignment can also destroy the old `Impl`, so it too has to be defined in the `.cpp` file.

This *Mandates* turns the most common pimpl mistake into a compile error. Directly `delete`ing a pointer to an incomplete class type was, before C++26, undefined behavior if the class had a non-trivial destructor, and compilers gave at most a warning; since C++26 it is ill-formed ([[expr.delete#4]], [[P3144R2]]).

`default_delete` is an empty class that also has a converting constructor: ¶1 `default_delete<T>` can be constructed from `default_delete<U>` whenever `U*` is implicitly convertible to `T*`. That is what allows `unique_ptr<Base>` to be constructed from `unique_ptr<Derived>`.

The array version `default_delete<T[]>` ([unique.ptr.dltr.dflt1]) calls `delete[]`. Its `operator()` is a template, and ¶3 requires `U(*)[]` to be convertible to `T(*)[]`. Between pointers to arrays only adding cv-qualification is allowed, so it accepts only `T*` and less cv-qualified pointers, and rejects pointers to derived classes.

## Construction [unique.ptr.single.ctor]

- The default and `nullptr_t` constructors (¶1–¶4) require `D` not to be a pointer type and to be default constructible. `unique_ptr<int, void(*)(int*)> p;` does not compile: a value-initialized function pointer deleter is a null pointer, and calling it later would be undefined behavior, so such construction is simply disallowed.
- `explicit unique_ptr(type_identity_t<pointer> p)` (¶5–¶8). `explicit` prevents a `T*` from silently becoming ownership; `type_identity_t` disables class template argument deduction, so `std::unique_ptr p(new int);` is {{ill-formed}}, because `new int` and `new int[n]` cannot be told apart from an `int*`.
- The two `(p, d)` constructors (¶9–¶13) copy the deleter from `const D&` and move it from `D&&` respectively, with the precondition that this construction does not throw. ¶13 specifies that when `D` is a reference type, the constructor taking an rvalue is defined as deleted. In the example in ¶14, `unique_ptr<int, const D&> p4(new int, D());` is wrong: it would bind the reference to a temporary deleter.
- The move constructor (¶15–¶18): when `D` is a reference, the reference is copied; otherwise the deleter is moved.
- The converting move constructor `unique_ptr(unique_ptr<U, E>&&)` (¶19–¶22) requires: ¶19.1 `unique_ptr<U, E>::pointer` is implicitly convertible to `pointer`; ¶19.2 `U` is not an array; ¶19.3 if `D` is a reference, `E` is the same as `D`, otherwise `E` is implicitly convertible to `D`.

## Destruction [unique.ptr.single.dtor]

¶1 The destructor is equivalent to `if (get()) get_deleter()(get());`, so the deleter is never called with a null pointer, and problems like `fclose(nullptr)` cannot occur. ¶2 If the deleter throws an exception, the behavior is undefined.

The converting constructor checks only whether the pointer is convertible, not whether the destructor is virtual:

```cpp run ub
#include <memory>
#include <string>
struct Base { ~Base() {} };   // non-virtual destructor
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
  std::unique_ptr<Base> p = std::make_unique<Derived>();   // compiles
}   // UB: deleting an object of dynamic type Derived through Base*
```

`default_delete<Base>` performs `delete` on a `Base*` while the object's dynamic type is `Derived`, and `Base`'s destructor is not virtual; by [[expr.delete]] this is undefined behavior. In our tests, compiled with `-fsanitize=address` and run with `ASAN_OPTIONS=detect_leaks=1`, LeakSanitizer reports that the buffer of `Derived::s` leaked, which is just one of the possible consequences. `shared_ptr` does not have this problem; it records how to delete according to the actual type at construction ([[util.smartptr.shared]]).

## Assignment [unique.ptr.single.asgn]

¶3 The effect of move assignment is:

```cpp
reset(u.release());
get_deleter() = std::forward<D>(u.get_deleter());
```

¶4 If `this != addressof(u)`, `u.get() == nullptr` after the assignment; otherwise `u.get()` is unchanged. So self-move-assignment is safe: `release` hands over the pointer and `reset` takes the same pointer back.

Doing `reset` before assigning the deleter causes trouble in a linked list:

```cpp run ub
#include <memory>
#include <utility>

struct Node {
  std::unique_ptr<Node> next;
  int v;
};

constexpr int pop_bad() {
  auto head = std::make_unique<Node>(
      std::make_unique<Node>(nullptr, 2), 1);
  head = std::move(head->next);   // UB
  return head->v;
}

constexpr int pop_good() {
  auto head = std::make_unique<Node>(
      std::make_unique<Node>(nullptr, 2), 1);
  head = std::exchange(head->next, nullptr);   // OK
  return head->v;
}

static_assert(pop_good() == 2);
int main() { return pop_bad() == 2 ? 0 : 1; }   // looks fine at run time
```

In `head = std::move(head->next)`, `u` is the member `next` of the old head node. When `reset` deletes the old head node, `u` is destroyed with it, and the following `u.get_deleter()` accesses an object that has already been destroyed. When the deleter is an empty class, this access usually does not really read memory, so nothing shows at run time, and AddressSanitizer does not catch it either.

Constant evaluation does check this kind of error. Putting `pop_bad()` in a `static_assert`, Clang 23 reports a member function call on a heap object that has been deleted. `pop_good` first moves `next` into a temporary with `std::exchange` and then assigns that to `head`, which avoids the problem.

¶6–¶10 Converting move assignment requires the pointer to be implicitly convertible, `U` not to be an array, and `is_assignable_v<D&, E&&>` to be true. ¶11 `operator=(nullptr_t)` is equivalent to `reset()`.

## Observers [unique.ptr.single.observers]

- `operator*` (¶1–¶4): ¶1 requires `*declval<pointer>()` to be valid, so `operator*` of `unique_ptr<void>` does not cause a hard error in overload resolution ([[LWG4324]]). ¶2 If `pointer`'s `operator*` returns a prvalue, `T&` would bind to a temporary and dangle, so that combination is ill-formed ([[LWG4148]]). ¶3 The precondition is `get() != nullptr`. Its `noexcept` follows `*declval<pointer>()`.
- `operator->` (¶5–¶7): the precondition is also `get() != nullptr`.
- `get()` returns the stored pointer, `get_deleter()` returns a reference to the deleter, and `explicit operator bool()` returns `get() != nullptr`.

Both preconditions are ordinary preconditions, not C++26 hardened preconditions, so even a hardened implementation does not guarantee to check dereferencing an empty `unique_ptr`.

## Modifiers [unique.ptr.single.modifiers]

¶1–¶2 `release()` gives up ownership and returns the pointer without calling the deleter. Not catching the return value is a memory leak.

¶3 The order in `reset(p)` is specified:

!!! std "[unique.ptr.single.modifiers]/3"
    Assigns p to the stored pointer, and then, with the old value of the stored pointer, old_p, evaluates `if (old_p) get_deleter()(old_p);`

`p` is stored first, then the deleter is called with the old value `old_p`. Note 1 explains why: calling the deleter might destroy `*this` itself, for example when `*this` is a member of the object being deleted. With the pointer updated first, `*this` is in a consistent state during and after the deleter runs, and nothing is deleted twice. Note 2 adds that in this case the postcondition `get() == p` does not hold, because `this->get()` is no longer a valid expression. ¶5 A deleter that throws is undefined behavior.

¶6–¶7 `swap` exchanges the pointers and the deleters; the precondition is that the deleters are swappable and do not throw when swapped.

## The array version `unique_ptr<T[], D>` [unique.ptr.runtime]

¶1 How the array version differs from the primary template:

- ¶1.1 Conversions that are not allowed between pointers to arrays are likewise not allowed between the corresponding `unique_ptr<T[], D>`; neither are conversions between array and non-array versions. These conversions make the program ill-formed.
- ¶1.2 The constructors and `reset` reject pointers to classes derived from `T`.
- ¶1.3–¶1.4 There is no `operator*` or `operator->`; there is `operator[]`.
- ¶1.5 The default deleter calls `delete[]`.

¶3 `T` must be a complete type, unlike the single-object version.

Converting an array of derived objects to an array of base objects is forbidden because subscripting advances the pointer by the size of the static type: after `Base* p = new Derived[3];`, `p[1]` accesses the wrong address, and `delete[] p` is undefined behavior ([[expr.delete]]). The rule is written as whether `V(*)[]` is convertible to `element_type(*)[]`; between pointers to arrays only qualification conversions are allowed ([[conv.qual]]), which rules out exactly the derived-to-base conversion.

```cpp run ok
#include <memory>
#include <type_traits>
struct B {};
struct D : B {};
using std::unique_ptr;
// adding const: OK
static_assert(std::is_convertible_v<unique_ptr<int[]>,
                                    unique_ptr<const int[]>>);
// derived to base: rejected
static_assert(!std::is_convertible_v<unique_ptr<D[]>, unique_ptr<B[]>>);
static_assert(!std::is_constructible_v<unique_ptr<B[]>, D*>);
// between array and non-array: rejected
static_assert(!std::is_convertible_v<unique_ptr<int[]>, unique_ptr<int>>);
static_assert(std::is_constructible_v<unique_ptr<const int[]>, int*>);
int main() {}
```

The constraints of the constructors ([unique.ptr.runtime.ctor] ¶2, ¶4, ¶6), converting assignment ([unique.ptr.runtime.asgn] ¶2) and `reset` ([unique.ptr.runtime.modifiers] ¶3) are all variations of this rule. Note that this `V*` conversion is allowed only when `pointer` is `element_type*`; with a fancy pointer, the types must be exactly the same.

[unique.ptr.runtime.observers] ¶1 The precondition of `operator[](i)` is that `i` is less than the number of elements in the array. `unique_ptr<T[]>` does not know how long the array is, so the standard cannot check it.

!!! impl "libc++ uses the array cookie for bounds checking"
    The Itanium C++ ABI specifies that when `T` has a non-trivial destructor, `new T[n]` stores the element count in front of the array, called the array cookie, for use by `delete[]`. In hardened mode (`fast` and above), libc++ reads it to check the index of `operator[]` when the default deleter is used and a cookie exists. In our tests: accessing index 3 after `make_unique<std::string[]>(3)` traps and terminates the program in `fast` mode; accessing index 3 after `make_unique<int[]>(3)` goes undetected, because `int` has a trivial destructor and there is no cookie. libc++ also has an ABI configuration `_LIBCPP_ABI_BOUNDED_UNIQUE_PTR` that stores the length separately and changes the layout; it is not enabled by default.

## Creation functions [unique.ptr.create]

| Call | Applicable `T` | Returns |
|---|---|---|
| ¶1–¶2 `make_unique<T>(args...)` | Not an array | `unique_ptr<T>(new T(std::forward<Args>(args)...))` |
| ¶3–¶4 `make_unique<T[]>(n)` | Array of unknown bound | `unique_ptr<T>(new remove_extent_t<T>[n]())`, value-initialized |
| ¶5 `make_unique<T[N]>(...)` | Array of known bound | Deleted |
| ¶6–¶7 `make_unique_for_overwrite<T>()` | Not an array | `unique_ptr<T>(new T)`, default-initialized |
| ¶8–¶9 `make_unique_for_overwrite<T[]>(n)` | Array of unknown bound | `unique_ptr<T>(new remove_extent_t<T>[n])` |
| ¶10 `make_unique_for_overwrite<T[N]>(...)` | Array of known bound | Deleted |

`make_unique` uses parentheses, `new T(args...)`. Since C++20 parentheses can also initialize aggregates ([[dcl.init]]), but they never select an `initializer_list` constructor: `make_unique<vector<int>>(3, 1)` gives three 1s, not `{3, 1}`.

The `()` in `make_unique<T[]>(n)` means value-initialization, so `make_unique<double[]>(1'000'000)` zeroes a million `double`s. If they are about to be overwritten anyway, that step is wasted, so C++20 added `make_unique_for_overwrite` ([[P1020R1]]). It default-initializes, and elements of trivial types have indeterminate values. C++26 changed uninitialized automatic variables to erroneous values, but dynamically allocated objects still have indeterminate values ([[basic.indet]]).

`make_unique` has no version that accepts a custom deleter or allocator.

In C++14, one reason to recommend `make_unique` was exception safety: `f(unique_ptr<T>(new T), g())` could evaluate `new T` first, then a throwing `g()`, causing a leak. C++17 specifies that the initializations of the parameters are not interleaved ([[expr.call]]), so this leak can no longer happen. Today `make_unique` is used to avoid writing `new` and to avoid repeating the type name.

Since C++23, almost all operations of `unique_ptr` and `make_unique` are `constexpr` ([[P2273R3]]):

```cpp run ok
#include <memory>
constexpr int f() {
  auto p = std::make_unique<int>(20);
  auto q = std::make_unique<int[]>(3);   // value-initialized: all zeros
  q[1] = 22;
  return *p + q[0] + q[1];
}
static_assert(f() == 42);
int main() {}
```

## Comparison, hashing and output

[unique.ptr.special] ¶1–¶2 `swap(x, y)` requires `is_swappable_v<D>`; its effect is `x.swap(y)`.

¶3 `==` compares `get()`. ¶4–¶7 `<` compares with `less<CT>`, where `CT` is the common type of the two `pointer` types. The built-in `<` on unrelated objects gives an unspecified result, while `std::less` always yields an implementation-defined strict total order over pointers ([[comparisons.general]]), so comparisons between `unique_ptr`s always form a total order. ¶11 `<=>` uses `compare_three_way`, also a total order. ¶12–¶18 define the various comparisons with `nullptr`.

`hash<unique_ptr<T, D>>` ([[util.smartptr.hash#1]]) is enabled only when `hash<pointer>` is enabled, and its value equals `hash<pointer>()(p.get())`.

[unique.ptr.io] `os << p` requires `os << p.get()` to be valid; its effect is to output `p.get()`.

## ABI: passing `unique_ptr` by value is not free

`sizeof(unique_ptr<T>) == sizeof(T*)`, but under the Itanium C++ ABI (Linux, macOS), a type with a non-trivial destructor or non-trivial copy or move constructor cannot be passed in registers. The caller constructs a temporary on the stack and passes its address; after the callee returns, the caller still has to destroy that moved-from temporary. So calling `void sink(std::unique_ptr<T> p)` costs one more memory write, one more memory read and one more destructor check than calling `void sink(T* p)`.

libc++ has an ABI configuration `_LIBCPP_ABI_ENABLE_UNIQUE_PTR_TRIVIAL_ABI` that adds Clang's `[[clang::trivial_abi]]` attribute to `unique_ptr` so it can be passed in registers. It is on by default in libc++ ABI version 2, but mainstream platforms use ABI version 1 for binary compatibility, where it is off.

## Questions

!!! question "Question 1"
    Why does `unique_ptr<T>` allow `T` to be incomplete, while `unique_ptr<T[]>` requires `T` to be complete?

<details markdown="1">
<summary>Answer</summary>

The class definition of the single-object version does not need `sizeof(T)`; it only stores a `T*`. What needs a complete type is destruction, guarded by the *Mandates* of `default_delete::operator()`. The conversion rules of the array version have to decide whether `V(*)[]` is convertible to `T(*)[]`, and `operator[]` does pointer arithmetic; all of this needs a complete `T`, so [unique.ptr.runtime.general] ¶3 makes it an overall requirement.
</details>

!!! question "Question 2"
    What is wrong with `std::unique_ptr<FILE, int(*)(FILE*)> f(std::fopen("x", "r"), &std::fclose);`?

<details markdown="1">
<summary>Answer</summary>

At least three things. First, the `unique_ptr` becomes two pointers in size, and calls through the function pointer are hard to inline. Second, except for the few functions explicitly designated addressable, taking the address of a standard library function has unspecified behavior and may even be ill-formed ([[namespace.std]]). Third, the return value of `fclose` is discarded, so an error flushing the write buffer is swallowed. A null pointer from a failed `fopen` is not a problem: the destructor does not call the deleter with a null pointer. A better way is a stateless function object: `struct fcloser { void operator()(FILE* f) const noexcept { std::fclose(f); } };`.
</details>

!!! question "Question 3"
    Why does `std::unique_ptr<int, void(*)(int*)> p;` not compile?

<details markdown="1">
<summary>Answer</summary>

[unique.ptr.single.ctor] ¶1 requires `is_pointer_v<deleter_type>` to be false. A value-initialized function pointer deleter is a null pointer; if you later `reset(new int)` and then destroy it, a null function pointer is called. The standard chooses to rule out this construction at compile time.
</details>
