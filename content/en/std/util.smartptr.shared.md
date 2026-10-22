---
title: shared_ptr
summary: "The full contract of shared_ptr: construction from raw pointers, deleters, aliases, weak_ptr and unique_ptr; the uniform definition of assignment and reset; observers; initialization and destruction in the make_shared family; comparison and the four pointer casts."
updated: 2026-10-19
---

!!! tldr
    - A `shared_ptr` stores a pointer and owns an object; the two can differ (the aliasing constructor). A `shared_ptr` that owns nothing is called empty, which is not the same as `get() == nullptr`.
    - When constructing from a raw pointer, the deleter remembers the argument's static type, so `shared_ptr<Base>(new Derived)` destroys correctly even if the destructor is not virtual.
    - Every construction from a raw pointer creates a new ownership group. Handing the same raw pointer to two `shared_ptr`s, or writing `shared_ptr<T>(static_cast<T*>(r.get()))`, deletes twice.
    - Assignment and `reset` are both defined as constructing a temporary and then `swap`ping.
    - `make_shared` initializes the object with parentheses and allocates only once; array elements are constructed in ascending address order and destroyed in reverse.

In implementation terms, a `shared_ptr` is two pointers: one to the object, one to a control block on the heap (holding the reference counts, deleter and allocator). That physical model and the thread-safety rules are covered in [[util.sharedptr]]. In the latest draft almost all members of `shared_ptr` are `constexpr` (C++26, [[P3037R6]]); libc++ (with Clang 23) does not implement this yet.

## Stored pointer and ownership [util.smartptr.shared.general]

¶1 `shared_ptr` stores a pointer, usually obtained via `new`, and implements shared ownership: a group of `shared_ptr`s jointly own an object, and the last owner is responsible for destroying the object or releasing the associated resources. A `shared_ptr` that owns no pointer is called **empty** ([[g:empty-shared-ptr]]).

The stored pointer (the return value of `get()`) and the owned pointer are usually the same, but the standard allows them to differ; the aliasing constructor below is an example. So empty is not the same as `get() == nullptr`: an empty `shared_ptr` can store a non-null pointer, and a non-empty `shared_ptr` can own a null pointer.

The member type `element_type` is `remove_extent_t<T>`; for example, the `element_type` of `shared_ptr<int[]>` is `int`.

¶2 `shared_ptr` meets *Cpp17CopyConstructible*, *Cpp17CopyAssignable* and *Cpp17LessThanComparable*, so it can be put in standard containers, and it is contextually convertible to `bool`. ¶3 `T` may be an incomplete type; Note 1 points out it may even be a function type.

¶5 For the purpose of determining data races, member functions access only the `shared_ptr` and `weak_ptr` objects themselves, not the objects they point to; see [[util.sharedptr]].

¶6 Several constraints in this subclause use **compatible** ([[g:compatible-pointer-type]]): `Y*` is said to be compatible with `T*` if `Y*` is convertible to `T*`, or `Y` is `U[N]` and `T` is cv `U[]`. The second half lets `shared_ptr<int[5]>` convert to `shared_ptr<int[]>`, even though `int(*)[5]` is not implicitly convertible to `int(*)[]`.

## Construction from a raw pointer [util.smartptr.shared.const]

### The deleter remembers Y (¶2–¶8)

```cpp run title="type-erasure.cpp" ok
#include <memory>
#include <string>
#include <cassert>
struct Base { ~Base() {} };                      // the destructor is not virtual
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
    std::shared_ptr<Base> p(new Derived);        // the deleter does delete (Derived*)
    std::shared_ptr<void> v = std::make_shared<Derived>();
    std::shared_ptr<Base> q = std::make_shared<Derived>();
    std::shared_ptr<Derived> d = std::static_pointer_cast<Derived>(q);
    assert(q.use_count() == 2);
}                                                // all destroyed correctly
```

Run under ASan in our tests, this produces no reports. `Base`'s destructor is not virtual, yet `p` correctly destroys the `Derived` and the string inside it.

The reason is the constructor's signature: `template<class Y> explicit shared_ptr(Y* p)`. The constructor remembers the argument type `Y`, not `T`, and the deleter in the control block performs `delete p` with `p` of type `Y*`. This differs from `unique_ptr<Base>`, which always `delete`s a `Base*` ([[unique.ptr]]). The prerequisite is that `Derived` is known at construction: `Base* b = new Derived; shared_ptr<Base> p(b);` remembers `Base` and is still UB.

¶2 Default construction gives an empty `shared_ptr` with `use_count() == 0 && get() == nullptr`. When constructing from `Y* p`:

- ¶3 *Constraints*: when `T` is not an array, `delete p` is well-formed and `Y*` is convertible to `T*`; when `T` is an array, `delete[] p` is well-formed and the array pointer types match.
- ¶4 *Mandates*: `Y` is a complete type.
- ¶5 *Preconditions*: the corresponding `delete` or `delete[]` has well-defined behavior and does not throw exceptions.
- ¶6 Effects: owns `p`; when `T` is an array, with a deleter that performs `delete[] p`. If an exception is thrown during construction (for example, allocating the control block fails), `delete p` is done first and then the exception propagates, so `shared_ptr<X>(new X)` does not leak.
- ¶7 Postconditions `use_count() == 1 && get() == p`; ¶8 may throw `bad_alloc`.

!!! ub "Handing the same raw pointer to two shared_ptrs"
    ```cpp run title="double-owner.cpp" ub
    #include <memory>
    int main() {
        int* raw = new int(42);
        std::shared_ptr<int> a(raw);
        std::shared_ptr<int> b(raw);   // a second ownership group
    }                                  // UB: raw is deleted twice
    ```

    Every construction from a raw pointer creates a new control block. `a` and `b` each think they are the sole owner, and each eventually `delete`s once. ASan reports `attempting double-free` in our tests. Formally it violates ¶5: at the second construction, `delete raw` does not have well-defined behavior, because `raw` will be deleted by the other group. When an object needs to obtain another `shared_ptr` to itself from inside, use [[util.smartptr.enab]].

### With a deleter and allocator (¶9–¶13)

```cpp
shared_ptr(Y* p, D d);           shared_ptr(Y* p, D d, A a);
shared_ptr(nullptr_t p, D d);    shared_ptr(nullptr_t p, D d, A a);
```

¶9 requires `D` to be move constructible and `d(p)` to be well-formed. ¶10 requires that copying or moving `d` does not throw, that `d(p)` has well-defined behavior and does not throw, and that `A` meets *Cpp17Allocator*. ¶11 The versions with an allocator use a copy of `a` to allocate memory for the control block; if an exception is thrown during construction, `d(p)` is called.

The deleter is called on the stored pointer even if that pointer is null:

```cpp run title="null-with-deleter.cpp" ok
#include <memory>
#include <cstdio>
int main() {
    std::shared_ptr<int> p(nullptr, [](int* q) {
        std::printf("deleter(%p)\n", (void*)q);
    });
    std::printf("use_count=%ld bool=%d\n", p.use_count(), bool(p));
}
```

In our tests it prints `use_count=1 bool=0` and then `deleter(0x0)`. `p` owns a null pointer and a deleter, so it is not empty, and on destruction it calls the deleter per [util.smartptr.shared.dest] ¶1.2. `unique_ptr`, by contrast, calls the deleter only when the pointer is non-null. So a deleter written for `shared_ptr` has to handle null pointers itself; `fclose(nullptr)`, for example, is UB in C.

### The aliasing constructor (¶14–¶17)

```cpp run title="aliasing.cpp" ok
#include <memory>
#include <cassert>
#include <string>
struct Person { std::string name; int age; };
int main() {
    auto p = std::make_shared<Person>("Ada", 36);
    std::shared_ptr<int> age(p, &p->age);   // owns the Person, points to a member
    assert(p.use_count() == 2 && *age == 36);
    p.reset();
    assert(*age == 36 && age.use_count() == 1);   // the Person is still alive
    std::shared_ptr<int> e(std::shared_ptr<int>(), age.get());
    assert(e && e.use_count() == 0);         // empty, but the stored pointer is non-null
}
```

¶14 `shared_ptr(const shared_ptr<Y>& r, element_type* p)` constructs a `shared_ptr` that stores `p` and shares ownership with `r`. ¶15 The rvalue version added in C++20 leaves `r` empty, saving one reference count increment and decrement.

The typical use is handing out a pointer to a member, an array element or another subobject while guaranteeing that the enclosing object is not destroyed first. The four pointer casts below are also implemented with the aliasing constructor.

¶16 Note 1 warns that the aliasing constructor does not check the relation between `p` and `r`; if `p` lives shorter than `r`'s ownership group, the result is a dangling pointer. ¶17 Note 2 points out that when `r` is empty, the result is an empty `shared_ptr` with a non-null stored pointer, like `e` in the example: it owns nothing, yet `operator bool` is true.

### Copy, move and other sources (¶18–¶29)

¶18–¶20 After copy construction, `get() == r.get()` and `use_count() == r.use_count()`; ¶21–¶23 after move construction, `*this` gets `r`'s old value, and `r` becomes empty with `r.get() == nullptr`. The template versions all require `Y*` to be compatible with `T*`.

¶24–¶27 `explicit shared_ptr(const weak_ptr<Y>& r)` shares ownership with `r` and copies its stored pointer. It throws `bad_weak_ptr` if `r.expired()`; the only difference from `r.lock()` is how it fails ([[util.smartptr.weak]]).

¶28–¶29 `shared_ptr(unique_ptr<Y, D>&& r)`: if `r.get()` is null, equivalent to default construction; otherwise equivalent to `shared_ptr(r.release(), std::move(r.get_deleter()))`, with `ref(r.get_deleter())` instead when `D` is a reference type. If an exception is thrown there are no effects, and `r` still owns the object.

Class template argument deduction works only from `weak_ptr` and `unique_ptr`; there is no deduction guide from a raw pointer, because `shared_ptr p(new int[3])` cannot tell `new T` from `new T[]`.

### Enabling shared_from_this (¶1)

¶1 defines **enables shared_from_this with `p`** ([[g:enables-shared-from-this]]): if `Y` has an unambiguous and accessible base class that is a specialization of `enable_shared_from_this`, the constructor performs

```cpp
if (p != nullptr && p->weak-this.expired())
  p->weak-this = shared_ptr<remove_cv_t<Y>>(*this, const_cast<remove_cv_t<Y>*>(p));
```

where *weak-this* is an exposition-only `weak_ptr` member of the base class. Only construction from `Y*` (including the two versions with a deleter, when `T` is not an array) and `make_shared`/`allocate_shared` do this; the aliasing constructor, copying and construction from `weak_ptr` do not, because they do not create a new ownership group. The last sentence of ¶1 points out that this assignment is not atomic. Details and pitfalls are in [[util.smartptr.enab]].

## Destruction, assignment and reset [util.smartptr.shared.dest] [util.smartptr.shared.assign] [util.smartptr.shared.mod]

The destructor ([util.smartptr.shared.dest] ¶1) has no side effects if `*this` is empty or `use_count() > 1`; otherwise it calls `d(p)` if there is a deleter `d`, and `delete p` if not.

All assignment operators are defined as constructing a temporary and then swapping: `operator=(r)` is equivalent to `shared_ptr(r).swap(*this)`. The same goes for `reset()`, `reset(p)`, `reset(p, d)` and `reset(p, d, a)`. This definition settles three things at once:

- self-assignment is safe;
- if constructing the temporary throws, `*this` is unchanged;
- the old object is released only when the temporary is destroyed, i.e. at the end of the statement.

[util.smartptr.shared.assign] ¶3 Note 1 adds that the count changes caused by the temporary are not observable side effects; the implementation need not actually create the temporary, and an assignment like `p = p;` may do nothing.

The same definition also shows that `sp.reset(sp.get())` is wrong: `shared_ptr(sp.get())` creates a second ownership group, and the result is a double delete.

## Observers [util.smartptr.shared.obs]

- ¶1 `get()` returns the stored pointer. ¶18 `operator bool` returns `get() != nullptr`; it does not indicate whether an object is owned.
- ¶2–¶7 The precondition of `operator*` and `operator->` is `get() != nullptr`. When `T` is an array or cv `void`, it is unspecified whether they are declared, but if they are, the declarations themselves must be well-formed. This lets implementations declare them unconditionally while `shared_ptr<void>` can still be instantiated.
- ¶8–¶12 `operator[](ptrdiff_t i)` is meaningful only for array `T`, with the precondition `get() != nullptr`. ¶9 adds two hardened preconditions: `i >= 0`; and `i < N` when `T` is `U[N]`. In a hardened implementation, violating them reports a contract violation with a terminating semantic ([[intro.compliance]]). When `T` is `U[]` the upper bound is unknown and only non-negativity can be checked. libc++ (with Clang 23) does not check either of them yet, even with `_LIBCPP_HARDENING_MODE_DEBUG`.
- ¶13–¶17 `use_count()` returns the number of `shared_ptr`s sharing ownership, 0 when empty, with no synchronization semantics. Note 3 points out that in multithreaded code this is only an approximation; `use_count() == 1` does not mean other threads have finished accessing the object.

¶19–¶22 `owner_before`, `owner_hash` and `owner_equal` compare by ownership rather than by stored pointer: a `shared_ptr` created by the aliasing constructor is `owner_equal` to the original, but `==` does not hold. They are what allows `weak_ptr` to be a container key; see [[util.smartptr.ownerless]]. `owner_before` and `owner_hash` are not `constexpr`, because they depend on the numeric value of the control block address.

## The make_shared family [util.smartptr.shared.create]

```cpp run title="make-shared.cpp" ok
#include <memory>
#include <vector>
#include <cassert>
int main() {
    auto v = std::make_shared<std::vector<int>>(3, 1);
    assert(v->size() == 3);                  // parentheses: three 1s
    auto a = std::make_shared<double[][2]>(6, {1.0, 0.0});
    assert(a[5][0] == 1.0);                  // every double[2] is {1, 0}
    auto b = std::make_shared<int[]>(4);
    assert(b[3] == 0);                       // value-initialized
}
```

`make_shared`, `allocate_shared`, `make_shared_for_overwrite` and `allocate_shared_for_overwrite` share the rules of ¶1–¶7:

- ¶3 Allocates memory for the object (for `U[N]` when `T` is `U[]`). The versions with an allocator use a copy of `a`, rebound to an unspecified `value_type`, in practice the control block type. If an exception is thrown there are no effects.
- ¶4 The return value `r` satisfies `r.get() != nullptr && r.use_count() == 1`.
- ¶7.1 Implementations should perform only one memory allocation, placing the object and the control block together (for the cost see [[util.sharedptr]]).
- ¶7.4 `make_shared` initializes with `::new(pv) U(args...)`, parentheses rather than braces, so `make_shared<vector<int>>(3, 1)` gives three 1s.
- ¶7.5 `allocate_shared` uses `allocator_traits<A2>::construct(a2, pu, args...)`, where `a2` is a copy of the allocator rebound to `remove_cv_t<U>` ([[LWG3216]]). So `polymorphic_allocator`'s uses-allocator construction applies to the object ([[allocator.uses]]).
- ¶7.8 The `_for_overwrite` versions use `::new(pv) U`, i.e. default-initialization, suitable for large buffers that are about to be overwritten wholesale.
- ¶7.9, ¶7.10 Array elements are initialized in ascending address order and destroyed in reverse; if initializing an element throws, the elements already constructed are destroyed in reverse order.
- ¶7.11, ¶7.12 Destruction mirrors construction: objects constructed by `allocate_shared` are destroyed with `allocator_traits<A2>::destroy`, others with `pu->~U()` ([[LWG4024]]).

The standard describes the case with no initial value given as the object having a default initial value; ¶7.6 specifies that this means `::new(pv) U()`, i.e. value-initialization. Do not confuse it with the default-initialization of `_for_overwrite`.

| Call | Form of `T` | Initial value |
|---|---|---|
| `make_shared<T>(args...)` (¶8–¶11) | Not an array | `T(std::forward<Args>(args)...)`, and enables shared_from_this |
| `make_shared<T>(N)` (¶12–¶14) | `U[]` | `N` elements, value-initialized |
| `make_shared<T>()` (¶15–¶17) | `U[N]` | Value-initialized |
| `make_shared<T>(N, u)` (¶18–¶20) | `U[]` | Every element is `u` |
| `make_shared<T>(u)` (¶21–¶23) | `U[N]` | Every element is `u` |
| `make_shared_for_overwrite<T>()` (¶24–¶26) | Not an array, or `U[N]` | Default-initialized |
| `make_shared_for_overwrite<T>(N)` (¶27–¶29) | `U[]` | Default-initialized |

Each row has a corresponding `allocate_shared` overload. ¶7.2 specifies that an initial value `u` of array type is interpreted element by element, so in `make_shared<double[][2]>(6, {1.0, 0.0})` every `double[2]` is `{1.0, 0.0}`. The array forms come from C++20's [[P0674R1]], and `_for_overwrite` from [[P1020R1]].

## Comparison [util.smartptr.shared.cmp]

¶1 `a == b` compares `a.get() == b.get()`; ¶2 `a == nullptr` is equivalent to `!a`. ¶3 `a <=> b` returns `compare_three_way()(a.get(), b.get())`, of type `strong_ordering`. `compare_three_way` gives a total order over arbitrary pointers, even ones pointing to unrelated objects, so `shared_ptr` can be used directly as a `std::set` key (¶4 Note 1).

All of these compare stored pointers, not ownership. To compare by ownership, use the `owner_*` functions above.

## Pointer casts [util.smartptr.shared.cast]

<div class="compare" markdown="1">

```cpp run ok
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};
int main() {
  std::shared_ptr<B> b(new D);
  auto d = std::static_pointer_cast<D>(b);
  // d shares ownership with b
}
```

```cpp run ub
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};
int main() {
  std::shared_ptr<B> b(new D);
  std::shared_ptr<D> d(
      static_cast<D*>(b.get()));
  // UB: a second ownership group
}
```

</div>

The program on the right reports `heap-use-after-free` under ASan in our tests: `d` deletes the object when destroyed, and `b` deletes it again.

`static_pointer_cast`, `dynamic_pointer_cast`, `const_pointer_cast` and `reinterpret_pointer_cast` each have a `const&` and a `&&` (C++20) version, and all return an aliasing construction:

```cpp
shared_ptr<T>(R, static_cast<typename shared_ptr<T>::element_type*>(r.get()))
```

where `R` is `r` or `std::move(r)`. The *Mandates* of each function is that the corresponding built-in cast is well-formed (¶1, ¶4, ¶8, ¶11). The note after each function warns that the seemingly equivalent `shared_ptr<T>(static_cast<T*>(r.get()))` would delete the same object twice.

¶5–¶6 `dynamic_pointer_cast` requires that `dynamic_cast` itself has well-defined behavior ([[expr.dynamic.cast]]). When `dynamic_cast` returns a null pointer, the result is a default-constructed empty `shared_ptr`, and in that case the rvalue version does not move from `r`.

`reinterpret_pointer_cast` is not `constexpr`, because `reinterpret_cast` cannot appear in constant evaluation.

## get_deleter [util.smartptr.getdeleter]

¶1 `get_deleter<D>(p)`: if `p` owns a deleter whose cv-unqualified type is `D`, returns its address; otherwise returns a null pointer. The returned pointer is valid at least as long as some `shared_ptr` owns that deleter; Note 1 says it is unspecified whether it remains valid longer, because the implementation might not destroy the deleter until all `weak_ptr`s are destroyed.

libc++ compares deleter types with `typeid`. In our tests, when compiling with `-fno-rtti`, libc++ does not declare `std::get_deleter` at all, and calling it gives a `no member named 'get_deleter'` error.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[util.smartptr.shared.general] ¶4 Example 1 shows declaring a `shared_ptr` in an `if` condition and initializing it with `dynamic_pointer_cast`.

[util.smartptr.shared.dest] ¶2 Note 1: after a `shared_ptr` is destroyed, the `use_count()` of every other `shared_ptr` sharing ownership with it is one less.

[util.smartptr.shared.mod] ¶1 and [util.smartptr.shared.spec] ¶1: the member `swap` exchanges the contents of two objects, and the non-member `swap(a, b)` is equivalent to `a.swap(b)`.

[util.smartptr.shared.cmp] ¶5: `a <=> nullptr` three-way compares `a.get()` with a null pointer of type `element_type*`.

[util.smartptr.shared.io] ¶1–¶2: `os << p` is equivalent to `os << p.get()` and returns `os`.

</details>

## Common misconceptions

!!! pitfall "`if (sp)` tests whether an object is owned"
    `operator bool` only looks at `get()`. The aliasing constructor can produce a `shared_ptr` that is true yet owns nothing, and constructing from a null pointer with a deleter can produce a `shared_ptr` that is false yet owns a resource. To test ownership, use `use_count() != 0`.

!!! pitfall "The deleter is called only when the pointer is non-null"
    That is the rule for `unique_ptr`. A `shared_ptr` calls the deleter on destruction even if the owned pointer is null.

## Questions

!!! question "Question 1"
    What is wrong with `std::shared_ptr<FILE> f(std::fopen(name, "r"), std::fclose);` when `fopen` fails?

<details markdown="1">
<summary>Answer</summary>

`fopen` returns `FILE*`, so the constructor selected is `shared_ptr(Y* p, D d)`, not the `nullptr_t` version. `p` happens to be a null pointer, and the resulting `shared_ptr` owns a null pointer with `use_count() == 1`. On destruction it calls `fclose(nullptr)` per [util.smartptr.shared.dest] ¶1.2, which is UB in C. The deleter should be written as `[](FILE* f) { if (f) std::fclose(f); }`. Besides, taking the address of the standard library function `std::fclose` is itself not guaranteed by the standard ([[namespace.std]]).
</details>

!!! question "Question 2"
    When `dynamic_pointer_cast<D>(std::move(r))` fails, does `r` still own the object?

<details markdown="1">
<summary>Answer</summary>

Yes. By ¶6.2, when `dynamic_cast` returns a null pointer the result is `shared_ptr<T>()`; the aliasing construction with `std::move(r)` as the argument is never performed, and `r` is not moved from. In our tests `assert(!e && r)` holds.
</details>

## Summary

| Operation | Key points |
|---|---|
| `shared_ptr<T>(new Y)` | The deleter remembers `Y`; creates a new ownership group |
| `shared_ptr<T>(p, d)` | Calls `d(p)` on destruction even if `p` is null |
| Aliasing constructor | What is stored is separate from what is owned; can be empty with a non-null pointer |
| Assignment, `reset` | Construct a temporary, then `swap` |
| `make_shared` | One allocation; parenthesized initialization; arrays constructed in ascending order, destroyed in reverse |
| `==`, `<=>` | Compare stored pointers |
| `*_pointer_cast` | Aliasing construction, sharing ownership with the original |
