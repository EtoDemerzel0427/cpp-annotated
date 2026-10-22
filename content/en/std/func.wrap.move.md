---
title: "Move-only wrapper: move_only_function"
summary: "C++23's move_only_function can hold non-copyable callable objects, its signature can carry const, & and noexcept, and calling an empty wrapper is undefined behavior rather than throwing."
updated: 2026-10-19
---

!!! tldr
    - `move_only_function` can only be moved, so the target object only needs to be constructible from the argument; a lambda capturing a `unique_ptr` can be held too.
    - The signature can carry `const`, `&`, `&&` and `noexcept`, which determine both how the wrapper's `operator()` is declared and how the target is called. `std::function`'s const hole therefore no longer exists.
    - When the signature has no `&`/`&&`, the target must be callable both as an lvalue and as an rvalue.
    - Calling an empty `move_only_function` violates a precondition and is undefined behavior; yet constructing one from an empty `std::function` does not give an empty wrapper.
    - `in_place_type` construction can hold types that cannot even be moved; such targets are always placed on the heap.

!!! warning "Implementation status"
    libc++ (LLVM 23) in our tests does not implement `move_only_function` yet; `__cpp_lib_move_only_function` in `<version>` is commented out. libstdc++ and MSVC STL already provide it. The examples on this page cannot be compiled with this setup, so they carry no verdict tags; you can try them on GCC with the godbolt button on the code block.

## Why it is needed

```cpp run title="mof-move-only.cpp"
#include <functional>
#include <memory>
#include <vector>

int main() {
    std::vector<std::move_only_function<int()>> tasks;
    tasks.emplace_back([p = std::make_unique<int>(42)] { return *p; });   // OK
    auto t = std::move(tasks.back());
    // auto u = t;                                    // error: not copyable
    return t() == 42 ? 0 : 1;
}
```

`std::function` requires its target to be copyable ([[func.wrap.func]]), so the lambda above, which captures a `unique_ptr`, cannot be put into it. Task queues, thread pools and callback registries often store exactly this kind of move-only object.

`move_only_function`'s approach is to make the wrapper itself move-only: since the wrapper is never copied, the target never needs to be copied either. When C++23 introduced it via [[P0288R9]], it also fixed two other problems of `std::function`: the signature cannot carry `const` and `noexcept`, and calling an empty wrapper costs a null check.

## const, ref-qualifiers and noexcept in the signature

Paragraph 1 of [func.wrap.move.general] specifies that the primary template `template<class... S> class move_only_function;` is not defined; there are only partial specializations of the form `move_only_function<R(ArgTypes...) cv ref noexcept(noex)>`:

- *cv* is `const` or empty;
- *ref* is `&`, `&&` or empty;
- *noex* is `true` or `false`.

That makes 12 combinations. The template argument is a qualified function type, such as `int() const` or `void(int) && noexcept`. In the core language such a type can only be used as the type of a member function or as a template argument, not to declare an ordinary function; it is colloquially called an abominable function type ([[g:abominable-function-type]], [[dcl.fct]]). The wrapper uses it precisely to encode the calling convention in the type.

The *cv ref* in the signature appears unchanged on the wrapper's `operator()`. Paragraph 2 additionally defines an exposition-only placeholder *inv-quals* ([[g:inv-quals]]) denoting **the qualifiers used to call the target**: *cv*`&` when *ref* is empty, and *cv ref* otherwise.

| Signature | Qualifiers of the wrapper's `operator()` | How the target is called |
|---|---|---|
| `R(A...)` | none | non-const lvalue |
| `R(A...) const` | `const` | const lvalue |
| `R(A...) &` | `&` | non-const lvalue |
| `R(A...) const &` | `const &` | const lvalue |
| `R(A...) &&` | `&&` | non-const rvalue |
| `R(A...) const &&` | `const &&` | const rvalue |

Note the first row: when the signature has no ref-qualifier, the wrapper's `operator()` can be called on both lvalues and rvalues, but the target is always called as an lvalue. This is consistent with how a member function without a ref-qualifier treats `*this` ([[over.match.funcs]]), and it also guarantees that such a wrapper can be called repeatedly.

## What it can hold: is-callable-from

Paragraph 1 of [func.wrap.move.ctor] defines the constraint *is-callable-from*<VT> ([[g:is-callable-from]]) shared by the constructors, where `VT` is the target type to be stored:

!!! std
    is_invocable_r_v<R, VT cv ref, ArgTypes...> && is_invocable_r_v<R, VT inv-quals, ArgTypes...>

When *noex* is true, both are replaced by `is_nothrow_invocable_r_v`. That is, the target must be callable in two ways, with the result convertible to `R`: once according to the signature's *cv ref*, and once according to *inv-quals*.

- When the signature carries `&` or `&&`, the two are the same, so it is just one condition.
- When the signature has no ref-qualifier, the first condition is `VT cv`. A first argument to `is_invocable` without a reference means an rvalue, so this checks calling as an rvalue; the second condition, `VT cv&`, checks calling as an lvalue. The target must support both, so function objects with only `operator()() &` or only `operator()() &&` are rejected.

Intuitively, a wrapper without a ref-qualifier promises to the outside that it can be called as both an lvalue and an rvalue, and the target it holds must withstand both kinds of call too.

### Fixing the const hole

```cpp run title="mof-const.cpp"
#include <functional>

int main() {
    auto counter = [n = 0]() mutable { return ++n; };

    std::move_only_function<int()> f = counter;            // OK: called as a non-const lvalue
    // std::move_only_function<int() const> g = counter;   // error: does not satisfy is-callable-from
    const auto& cf = f;
    // cf();                                                // error: operator() is not a const member
    return f() == 1 ? 0 : 1;
}
```

The problem with `std::function` is that a const wrapper calls the target in a non-const way. Here the two things are split into two types: to be callable on a const wrapper, write `int() const`, at the price of only holding targets callable as const lvalues; write `int()` and you can hold a `mutable` lambda, but the wrapper's `operator()` is not const either.

`noexcept` likewise becomes a real contract: `move_only_function<void() noexcept>` only accepts targets that are `is_nothrow_invocable`, and its `operator()` really is `noexcept`. `std::function` cannot express this.

## The converting constructor (¶4–¶9)

For `template<class F> move_only_function(F&& f)`, ¶4 lets `VT` be `decay_t<F>`:

| Element | Content |
|---|---|
| ¶5 Constraints | `F` is neither `move_only_function` itself nor a specialization of `in_place_type_t`; *is-callable-from*<VT> |
| ¶6 Mandates | `is_constructible_v<VT, F>` |
| ¶7 Preconditions | `VT` meets *Cpp17Destructible*; if `VT` is move-constructible, it also meets *Cpp17MoveConstructible* |
| ¶9 Throws | any exception thrown by the initialization of the target; unless `VT` is a function pointer or a `reference_wrapper`, it may also throw `bad_alloc` |

Compared with `std::function`, there is no copyability in the Mandates. ¶7 also only requires the semantic requirements of move construction when `VT` is movable, leaving room for non-movable targets later on.

¶8 The following three cases give an empty wrapper: `f` is a null function pointer; `f` is a null member pointer; `f` is an empty `move_only_function` or `copyable_function` specialization. In the other cases, the target is a `VT` direct-non-list-initialized with `std::forward<F>(f)`.

!!! pitfall "Constructing from an empty std::function does not give an empty wrapper"
    `std::function` is not in the list in ¶8. Constructing a `move_only_function<void()>` from an empty `std::function<void()>` gives a non-empty wrapper whose target is that empty `std::function`:

    ```cpp
    std::function<void()> empty;
    std::move_only_function<void()> m = empty;
    bool b = static_cast<bool>(m);   // true
    m();                             // not UB: the target is called, and it throws bad_function_call
    ```

    So a check like `if (m) m();` does not help here. When migrating old code where the source might be an empty `std::function`, check for emptiness before converting.

## Constructing directly inside the wrapper: in_place_type (¶10–¶21)

```cpp
template<class T, class... Args>
  explicit move_only_function(in_place_type_t<T>, Args&&... args);
template<class T, class U, class... Args>
  explicit move_only_function(in_place_type_t<T>, initializer_list<U> ilist, Args&&... args);
```

These two constructors construct the target object directly from `args...`, with no move in between. So the target can be a non-movable type, such as a function object with a `std::mutex` member:

```cpp run title="mof-in-place.cpp"
#include <functional>
#include <mutex>
#include <utility>

struct Guarded {
    std::mutex m;                   // Guarded can be neither copied nor moved
    int n;
    explicit Guarded(int start) : n(start) {}
    int operator()() { std::lock_guard lk(m); return ++n; }
};

int main() {
    std::move_only_function<int()> f(std::in_place_type<Guarded>, 41);
    // std::move_only_function<int()> g = Guarded(41);   // error: violates Mandates, Guarded cannot be constructed from an rvalue
    auto h = std::move(f);   // OK: only ownership is transferred
    return h() == 42 ? 0 : 1;
}
```

The last line works because a non-movable target cannot be placed in the wrapper's inline buffer (otherwise the wrapper itself could not be moved); it is always on the heap, and moving the wrapper only transfers a pointer.

Key points of the specification:

- ¶11, ¶17 Constraints: `VT` is constructible from `Args...` (or `initializer_list<U>&, Args...`) and satisfies *is-callable-from*<VT>.
- ¶12, ¶18 Mandates: `VT` (that is, `decay_t<T>`) must be the same type as `T`. `in_place_type<const Foo>` and `in_place_type<Foo&>` are both ill-formed.
- The constructors are `explicit`, to keep copy-list-initialization from selecting them unintentionally.

## Calling an empty wrapper is undefined behavior

[func.wrap.move.inv] paragraph 1: `explicit operator bool()` returns true when there is a target. Paragraphs 2–3 specify the call:

!!! std
    *Preconditions*: \*this has a target object.

The effect is equivalent to `return INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...);`, where `f` is an lvalue designating the target and `F` is its type.

| | `std::function` | `move_only_function` |
|---|---|---|
| Calling an empty wrapper | throws `bad_function_call` | violates a precondition, {{ub}} |
| Cost of a call | every call implies a null check, or an empty-call function that throws instead | no null check needed |
| `noexcept` signatures | cannot be expressed | `noexcept(noex)` holds |

```cpp
std::move_only_function<void()> m;
m();   // UB: violates the precondition
```

This is an ordinary precondition, not one of C++26's hardened preconditions ([[structure.specifications]]), so even in a hardened implementation ([[g:hardened-implementation]]) the standard does not require it to be checked.

`static_cast<F inv-quals>(f)` means the target is called as an rvalue when the signature carries `&&`. This is suitable for expressing tasks that can only be called once:

```cpp run title="mof-rvalue.cpp"
#include <functional>
#include <string>
#include <utility>

struct OneShot {
    std::string payload = "hello";
    std::string operator()() && { return std::move(payload); }   // callable only on rvalues
};

int main() {
    std::move_only_function<std::string() &&> f = OneShot{};
    // f();                           // error: operator() is &&-qualified and f is an lvalue
    std::string s = std::move(f)();   // OK: the target is called as OneShot&&
    return s == "hello" ? 0 : 1;
}
```

After the call the wrapper is still non-empty, and `operator bool` is still true. "Callable only once" is a convention in the code; the type does not enforce it.

## Assignment, destruction and utility functions

- ¶22 Move assignment is equivalent to `move_only_function(std::move(f)).swap(*this)`; the standard does not mark it `noexcept`.
- ¶24 `operator=(nullptr_t) noexcept` destroys the target (if any).
- ¶26 `template<class F> operator=(F&&)` is equivalent to `move_only_function(std::forward<F>(f)).swap(*this)`.
- ¶28 The destructor destroys the target (if any).

[func.wrap.move.util] provides a member `swap` and two hidden friends ([[g:hidden-friend]]): a non-member `swap` and `operator==(const move_only_function&, nullptr_t)`. Hidden friends can only be found by argument-dependent lookup and do not appear in the namespace's ordinary overload sets. `!=` and `nullptr == m` are synthesized by C++20's rewritten candidates.

Unlike `std::function`, `move_only_function` has no copy operations, no `target()`/`target_type()`, and no deduction guides.

## Small-object optimization

Paragraph 2 of [func.wrap.move.class] recommends that implementations avoid dynamic allocation for small target objects, and Note 1 adds a restriction:

!!! std
    Such small-object optimization can only be applied to a type T for which is_nothrow_move_constructible_v<T> is true.

This note is a consequence, not an additional rule. `move_only_function`'s move constructor is `noexcept` ([func.wrap.move.ctor] paragraph 3). When the target is in the inline buffer, moving the wrapper means moving the target; if the target's move may throw, the `noexcept` cannot be honored. When the target is on the heap, only a pointer needs to be transferred.

## Conversions between wrappers

¶8 counts an empty `copyable_function` as empty too, which shows that the standard expects wrappers to be converted into one another. Paragraph 3 of [[func.wrap]] recommends that implementations avoid double wrapping in such conversions, for example taking over the internal storage directly when constructing a `move_only_function` from a `copyable_function`. Paragraph 2 allows the by-value arguments of nested wrappers to alias each other, so in this case the number of times an argument is copied is unspecified.

## Questions

!!! question "Question 1"
    Which of the following types can be held by `std::move_only_function<void()>`?
    ```cpp
    struct A { void operator()() &; };
    struct B { void operator()() &&; };
    struct C { void operator()() const; };
    struct D { void operator()(); };
    ```

<details markdown="1">
<summary>Answer</summary>

The signature has no ref-qualifier, so *is-callable-from* requires both `is_invocable_r_v<void, VT>` (rvalue) and `is_invocable_r_v<void, VT&>` (lvalue) to hold.

- `A` can only be called as an lvalue: no;
- `B` can only be called as an rvalue: no;
- `C`'s const member function can be called on any value category: yes;
- `D` has no ref-qualifier, so it can be called as both an lvalue and an rvalue: yes.

To hold `A`, use `move_only_function<void() &>`; to hold `B`, use `move_only_function<void() &&>`.
</details>

!!! question "Question 2"
    Why does `in_place_type<T>` construction require `decay_t<T>` to be exactly the same as `T`, rather than decaying automatically like the converting constructor?

<details markdown="1">
<summary>Answer</summary>

`in_place_type<T>` means "construct an object of type `T` inside the wrapper". If `T` were `const Foo` or `Foo&` and quietly decayed, the type actually stored would not match what was written: with `const` lost, the call would no longer be on a const object; with a reference turned into a value, the intent to refer to an external object would yield a copy instead. Rather than silently change the meaning, it is better to reject it outright. The argument of the converting constructor is an existing expression, and decaying it when storing by value is the natural outcome.
</details>
