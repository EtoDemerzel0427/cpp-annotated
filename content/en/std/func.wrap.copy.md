---
title: "Copyable wrapper: copyable_function"
summary: "C++26's copyable_function redoes std::function along the lines of move_only_function: it is copyable, its signature can carry const, & and noexcept, and calling an empty wrapper is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - `copyable_function` is a copyable `move_only_function`: the signature qualifiers, *inv-quals*, *is-callable-from* and "calling empty is UB" rules are all the same.
    - It requires the target to be copyable. As with `std::function`, this is Mandates: `is_constructible` being true does not mean construction actually works.
    - When migrating from `std::function`, you have to write `copyable_function<void() const>` to be able to call it in a const member function; writing just `void()` compiles, but gives no const-correctness.
    - Constructing it from an empty `std::function` gives a non-empty wrapper; a `move_only_function` cannot be used to construct it at all.

!!! warning "Implementation status"
    libc++ (LLVM 23) in our tests does not implement `copyable_function` yet; `__cpp_lib_copyable_function` in `<version>` is commented out. The examples on this page cannot be compiled with this setup, so they carry no verdict tags.

## The gap it fills

C++23 got a const-correct, `noexcept`-capable [[func.wrap.move|move_only_function]], but it cannot be copied. Places that need to copy callbacks, such as configuration objects that get copied or handlers distributed to multiple subscribers, could only fall back on `std::function` with its const hole ([[func.wrap.func]]). `copyable_function` ({{c++26}}, [[P2548R6]]) fills this gap.

Its wording is an almost verbatim copy of [func.wrap.move], plus the copy operations. The following are exactly the same as for `move_only_function`; see [[func.wrap.move]] for details:

- [func.wrap.copy.general]: the 12 partial specializations `R(ArgTypes...) cv ref noexcept(noex)` and the definition of *inv-quals*;
- [func.wrap.copy.class] paragraph 2: the recommended small-object optimization, applicable only to nothrow-movable types;
- [func.wrap.copy.ctor] paragraph 1: the constraint *is-callable-from*;
- [func.wrap.copy.inv]: calling an empty wrapper violates a precondition ({{ub}}), and the effect of a call is `INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...)`;
- [func.wrap.copy.util]: a member `swap`, and hidden friends `swap` and `operator==(f, nullptr)`;
- no `target()`/`target_type()`, and no deduction guides.

## Migrating from std::function

```cpp run title="copyable-migrate.cpp"
#include <functional>

struct Button {
    std::copyable_function<void() const> on_click;
    void click() const { on_click(); }        // OK: operator() is const
};

struct Button2 {
    std::copyable_function<void()> on_click;
    void click() const { /* on_click(); */ }  // error if uncommented: operator() is not const
};

int main() {
    int clicks = 0;
    Button b{[&clicks] { ++clicks; }};        // OK: the lambda itself can be called as const
    // Button bad{[n = 0]() mutable { ++n; }}; // error: a mutable lambda cannot be called as a const lvalue
    Button copy = b;                           // OK: copyable
    copy.click();
    b.click();
    return clicks == 2 ? 0 : 1;
}
```

Mechanically replacing `std::function<void()>` with `copyable_function<void()>` compiles: when the signature has no `const`, the target is called as a non-const lvalue, so `mutable` lambdas can still be held. But then the wrapper's `operator()` is not const either, and calling it in a const member function fails (`Button2` in the example). To call it in a const context, write `void() const` and accept that it can only hold targets that can be called in a const way.

Point by point:

| | `std::function<R(A...)>` | `std::copyable_function<R(A...) const>` |
|---|---|---|
| A const wrapper calling a non-const target | allowed (the const hole) | rejected at construction |
| `noexcept` signatures | cannot be expressed | `R(A...) const noexcept` |
| Calling an empty wrapper | throws `bad_function_call` | {{ub}} |
| Constructing from an empty `std::function` | gives an empty wrapper | gives a non-empty wrapper whose target is that empty `function` |
| `target()`, `target_type()` | yes | no |
| Class template argument deduction | yes | no |
| Copying a wrapper holding a function pointer | does not throw | may throw `bad_alloc` per the specification |

## Rules beyond move_only_function

### Copy construction (¶3–¶4)

¶3 If `f` has no target, neither does the result; otherwise the target is a copy of `f`'s target.

¶4 Throws: any exception thrown by the initialization of the target, and possibly `bad_alloc`, with no exceptions. `std::function`'s copy constructor is guaranteed not to throw when the target is a function pointer or a `reference_wrapper` ([[func.wrap.func]]); `copyable_function`'s converting constructor has this guarantee (¶11), but its copy constructor does not. If an implementation puts these two kinds of target in the inline buffer, copying naturally does not allocate, but the standard does not guarantee it.

¶24 Copy assignment is equivalent to `copyable_function(f).swap(*this)`, that is, copy then swap, giving the strong exception safety guarantee.

### Copyability is Mandates (¶7–¶11)

| Element | `move_only_function` | `copyable_function` |
|---|---|---|
| Constraints | not itself, not `in_place_type_t`, *is-callable-from* | the same (¶7) |
| Mandates | `is_constructible_v<VT, F>` | plus `is_copy_constructible_v<VT>` (¶8.2) |
| Preconditions | *Cpp17Destructible*; *Cpp17MoveConstructible* if movable | *Cpp17Destructible* and *Cpp17CopyConstructible* (¶9) |

As with `std::function`, copyability is in the Mandates: for a move-only lambda, `is_constructible_v<copyable_function<void()>, decltype(lambda)>` is true, and a hard error occurs only on actual construction. The reason is also the same: the wrapper's copy constructor must be able to copy any target it might hold, and the code to copy the target has to be instantiated at construction.

The same goes for `in_place_type` construction (¶12–¶23): its Mandates adds `is_copy_constructible_v<VT>` on top of `VT` being the same as `T`. The precondition *Cpp17CopyConstructible* includes *Cpp17MoveConstructible*, so `copyable_function` cannot hold non-movable types the way `move_only_function` can.

### When the wrapper is empty (¶10)

¶10 Three cases: a null function pointer, a null member pointer, an empty `copyable_function` specialization.

`move_only_function` is not in the list, and this is not an oversight: `move_only_function` is not copyable, violates ¶8.2, and cannot be used to construct a `copyable_function` at all. As with `move_only_function`, `std::function` is not in the list either: constructing from an empty `std::function` gives a non-empty wrapper, and calling it makes the inner `std::function` throw `bad_function_call`.

## Converting to and from other wrappers

- `copyable_function` to `move_only_function`: allowed. An empty `copyable_function` gives an empty `move_only_function` ([func.wrap.move.ctor] paragraph 8), and paragraph 3 of [[func.wrap]] recommends that implementations take over the internal storage directly to avoid double wrapping.
- `move_only_function` to `copyable_function`: ill-formed (Mandates).
- `copyable_function` to `function_ref`: allowed; the `function_ref` refers to this wrapper object itself ([[func.wrap.ref]]), so mind the lifetime.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶11 says that it may throw `bad_alloc` unless `VT` is a function pointer or a specialization of `reference_wrapper`; ¶17 and ¶23 (the two `in_place_type` constructors) say "a pointer or a specialization of `reference_wrapper`" instead. Literally, the latter covers all pointer types, but *is-callable-from* requires `VT` itself to be callable, and object pointers are not callable, so the only thing that can actually fall into this branch is a function pointer, and the two phrasings have the same effect. The corresponding paragraphs for `move_only_function` all say function pointer.

¶2 Default construction and `nullptr_t` construction give an empty wrapper. ¶5 Move construction is `noexcept`, and the moved-from object is in a valid but unspecified state. Move assignment, `nullptr` assignment, template assignment and the destructor in ¶26–¶32 are the same as for `move_only_function`.

</details>

## Questions

!!! question "Question 1"
    Why not just add partial specializations with `const`, ref-qualifiers and `noexcept` to `std::function`, instead of introducing a new name?

<details markdown="1">
<summary>Answer</summary>

Neither of the two existing behaviors of `std::function<R(A...)>` can be changed: its const `operator()` calls non-const targets, and tightening this would break all code that holds `mutable` lambdas and calls them in const contexts; throwing `bad_function_call` on an empty call is also behavior that existing code relies on, and changing it to UB would be a silent semantic break. If only new partial specializations such as `function<R(A...) const>` were added, different specializations of the same template would have completely different const semantics and empty-call semantics, which would be easy to confuse. A new name keeps the old and new semantics each self-consistent.
</details>

!!! question "Question 2"
    Is `std::is_constructible_v<std::copyable_function<void()>, std::move_only_function<void()>>` true or false?

<details markdown="1">
<summary>Answer</summary>

According to the standard, it is true. The trait reflects only the constraints: `move_only_function<void()>` is not a `copyable_function`, not an `in_place_type_t`, and its `operator()` has no ref-qualifier and is not const, so it can be called as both an lvalue and an rvalue, and *is-callable-from* holds. Non-copyability is a Mandates-level issue, reported only on actual construction. For standard library types, `is_constructible` being true does not mean the code compiles.
</details>
