---
title: Polymorphic function wrappers
summary: "A comparison of the four wrappers that use type erasure to hold any callable, function, move_only_function, copyable_function and function_ref: ownership, copyability, signature qualifiers, the empty state and overhead; plus bad_function_call and the argument aliasing permission when wrappers are nested."
updated: 2026-10-19
---

!!! tldr
    - All four wrappers use type erasure to put any callable into a type determined only by the call signature: `function` (C++11), `move_only_function` (C++23), `copyable_function` (C++26) and `function_ref` (C++26).
    - The first three own their target object; `function_ref` does not, is only two pointers in size and never allocates, but you have to ensure the target lives long enough yourself.
    - Only `function` throws `bad_function_call` when called empty. Calling an empty `move_only_function` or `copyable_function` violates a precondition, and `function_ref` has no empty state at all.
    - The three newer wrappers can put `const`, `&`/`&&` and `noexcept` in the signature, closing `function`'s const-correctness hole.
    - When one wrapper's target is another wrapper, the standard allows the two levels of calls to share a single by-value parameter object, so the number of copies is unspecified.

## One fixed type for any callable

```cpp run title="button.cpp" ok
#include <functional>
#include <cstdio>
class Button {
  std::function<void(int)> on_click_;     // the type depends only on the signature void(int)
public:
  void on_click(std::function<void(int)> f) { on_click_ = std::move(f); }
  void click(int x) { if (on_click_) on_click_(x); }
};
void log_click(int x) { std::printf("free %d\n", x); }
int main() {
  Button b;
  b.on_click(log_click);                                   // function pointer
  b.click(1);
  int count = 0;
  b.on_click([&count](int x) { count += x; });             // stateful lambda
  b.click(2); b.click(3);
  std::printf("count %d\n", count);                        // 5
}
```

Every lambda has its own unique closure type. A template can accept any callable, but a class that needs to store callbacks and does not want to become a template itself needs a fixed type to hold them.

The four **polymorphic function wrappers** ([[g:polymorphic-function-wrapper]]) in [func.wrap] solve exactly this problem. They use **type erasure** ([[g:type-erasure]]) to hide the concrete type of the target until run time, leaving only the call signature ([[func.def]]) in the type. Calls are all made via *INVOKE*&lt;R&gt; ([[func.require]]), so member pointers, function pointers and function objects can all be held, and the return value is discarded when `R` is `void`.

## The four wrappers

| Wrapper | Introduced | Page | Characteristics |
|---|---|---|---|
| `function<R(Args...)>` | C++11 | [[func.wrap.func]] | owning, copyable; throws when called empty; has a const-correctness hole |
| `move_only_function<R(Args...) cv ref noexcept(b)>` | C++23 | [[func.wrap.move]] | owning, move-only; the signature can carry cv, ref and noexcept |
| `copyable_function<R(Args...) cv ref noexcept(b)>` | C++26 | [[func.wrap.copy]] | copyable, the signature can carry qualifiers; in effect a fixed `function` |
| `function_ref<R(Args...) cv noexcept(b)>` | C++26 | [[func.wrap.ref]] | non-owning, two pointers in size, trivially copyable, suited to function parameters |

| Aspect | `function` | `move_only_function` | `copyable_function` | `function_ref` |
|---|---|---|---|---|
| Ownership | owns the target | owns | owns | does not own; stores only a pointer and a thunk |
| The wrapper itself | copyable | move-only | copyable | trivially copyable |
| Requirements on the target | must be copyable | may be move-only | must be copyable | none |
| `const` in the signature | not supported | supported | supported | supported |
| `&`, `&&` in the signature | not supported | supported | supported | not supported |
| `noexcept` in the signature | not supported | supported | supported | supported |
| Empty state | yes; calling throws `bad_function_call` | yes; calling violates a precondition {{ub}} | same | none; no default constructor |
| `target()`, `target_type()` | yes (needs RTTI) | no | no | no |
| Deduction guides | yes | no | no | yes |
| Provided in freestanding | no | no | no | yes |

Several differences deserve elaboration:

- The empty state. `function` defines calling an empty wrapper as throwing `bad_function_call`, so every call implies a null check (with libc++'s default ABI in our tests, the call code generated at `-O2` does contain a null-check branch, `cbz`; only with `_LIBCPP_ABI_OPTIMIZED_FUNCTION` is the empty state changed into a thunk that throws, eliminating this branch). The later `move_only_function` and `copyable_function` turned non-emptiness into a precondition, so implementations pay nothing for the empty state, which is also what makes `noexcept` signatures possible. `function_ref` simply disallows the empty state: it has no default constructor, and constructing it from a null function pointer violates a precondition.
- Const-correctness. `function::operator()` is a const member function, yet it can call the target's non-const `operator()`; see [[func.wrap.func]] for details. The new wrappers put `const` in the signature: `move_only_function<void() const>` only accepts targets that can be called as const lvalues.
- Ref-qualifiers. `move_only_function<void() &&>` means it can only be called as an rvalue, suited to one-shot tasks, and the target is also called as an rvalue. `function_ref` does not support ref-qualifiers, because it does not own the target and treating the target as an rvalue would make no sense.

## The cost of type erasure

An owning wrapper typically consists of three parts: an inline buffer ([[g:small-object-optimization]]) or a pointer to the heap, a function pointer that does the call, and a table of operations for copying, moving and destroying. This brings several costs:

1. One indirect call; the compiler generally cannot inline the target.
2. A possible heap allocation, when the target does not fit in the inline buffer. The standard recommends avoiding dynamic allocation for small objects; for `move_only_function` and `copyable_function`, a note says this optimization may only be applied to types that are nothrow movable. `function` must not throw when constructed from a function pointer or a `reference_wrapper`, which in effect requires it not to allocate.
3. Copying cost: copying a `function` deep-copies the target. Its move constructor is `noexcept`, so when it is in a `vector` that grows, it is moved rather than copied.
4. Size: libc++'s `std::function<int(int)>` is 32 bytes in our tests; `function_ref` is only two pointers in size.

`function_ref` has none of costs 2 and 3: its constructors are all `noexcept`, it never allocates, and copying it just copies two pointers. The cost moves to lifetime instead; see [[func.wrap.ref]].

!!! tip "How to choose"
    For callback parameters used only during the call, use `function_ref` or a template. If you need to store it and the target may be move-only (it captures a `unique_ptr` or a `promise`), use `move_only_function`. If you need to store it and the wrapper itself must be copyable, use `copyable_function`. `function` is kept mainly for compatibility with old interfaces.

## `bad_function_call` [func.wrap.badcall]

¶1 `bad_function_call` derives from `std::exception`. Only `function::operator()` throws it, when the wrapper has no target; the other three wrappers never throw it. ¶2 Its `what()` returns an implementation-defined string ({{impl}}).

```cpp run title="bad-call.cpp" ok
#include <functional>
#include <cstdio>
int main() {
  std::function<void()> f;          // empty
  try {
    f();
  } catch (const std::bad_function_call& e) {
    std::puts(e.what());            // implementation-defined content; prints std::bad_function_call in our tests
    return 0;
  }
  return 1;
}
```

In `-fno-exceptions` mode, libc++ does not throw but terminates the program directly.

## Wrappers within wrappers: the argument aliasing permission [func.wrap.general]

¶2 Consider a signature `void(T)` that takes its argument by value, with an outer wrapper whose target is another wrapper:

```cpp
move_only_function<void(T)> f{copyable_function<void(T)>{[](T) {}}};
T t;
f(t);   // how many times is T copied? The standard says: unspecified
```

By the ordinary rules, `f(t)` first copies `t` into the parameter of `f.operator()`, then forwards that parameter to the by-value parameter of the inner `copyable_function::operator()`, which in turn forwards it to the lambda's by-value parameter. Each additional layer of wrapping constructs one more object.

¶2 allows implementations to make the argument of the inner call be exactly the argument object at the same position and of the same type in the outer call, even if the corresponding parameter is not of reference type. In the core language, two by-value parameters are necessarily two different objects ([[expr.call]]), so this needs explicit authorization in the library wording. The consequence is that the number of copies is unspecified ({{unspec}}): if `T`'s copy constructor has observable side effects, you cannot rely on how many times it is called.

¶3 Recommended practice: implementations should avoid double wrapping ([[g:double-wrapping]]) when constructing one kind of wrapper from another. For example, when a `move_only_function` is constructed from a `copyable_function`, it should take over the inner one's storage and thunk directly rather than adding another layer on the outside. Removing a layer removes one pass by value, and the permission in ¶2 guarantees that this is valid in terms of observable behavior.

!!! lawyer "The limits of the permission"
    ¶2 applies only when the type of the target object is itself a specialization of one of these four wrappers. When the target is a hand-written forwarding function object, there is no aliasing permission at all, and arguments are initialized normally per [[expr.call]].

    The same type is also a hard condition. When a `function_ref<void(std::string&&)>` wraps a `function_ref<void(std::string)>`, the parameter types of the two levels differ and ¶2 does not apply; however, [[func.wrap.ref]] has a separate dedicated permission allowing the outer one to copy the inner one's two pointers directly.

## Implementation status

In the `<version>` of libc++ (LLVM 23) in our tests, `__cpp_lib_move_only_function`, `__cpp_lib_copyable_function` and `__cpp_lib_function_ref` are all commented out; these three wrappers are not implemented yet. libstdc++ and MSVC STL already provide `move_only_function`. Examples in [[func.wrap.move]], [[func.wrap.copy]] and [[func.wrap.ref]] that cannot be verified with this libc++ carry no verdict tag; you can try them on GCC trunk with the godbolt button on the code block.

## History and evolution

!!! history
    - C++11: `std::function` came into the standard from TR1 (originating in Boost.Function).
    - C++17: allocator support in `function` was removed ([[P0302R1]]), because implementations had never implemented it consistently; deduction guides were added.
    - C++23: `move_only_function` was added ([[P0288R9]]), putting cv, ref and noexcept into a wrapper signature for the first time.
    - C++26: `copyable_function` ([[P2548R6]]) and `function_ref` ([[P0792R14]]) were added.

## Questions

!!! question "Question 1"
    Why does `move_only_function` make calling an empty wrapper a precondition violation, rather than throwing `bad_function_call` as `function` does? What does this mean for `noexcept` signatures?

<details markdown="1">
<summary>Answer</summary>

If an empty call had to throw, the `operator()` of `move_only_function<void() noexcept>` could not be `noexcept`: it would either violate its own exception specification or have to terminate the program. With a precondition instead, implementations need no check for the empty state, the `noexcept(noex)` signature becomes possible, and non-empty calls also save the null-check branch. The price is that the error turns from a catchable exception into undefined behavior, and the caller has to ensure non-emptiness ([[func.wrap.move]]).
</details>

!!! question "Question 2"
    `T`'s copy constructor does `++copies`. After `move_only_function<void(T)> f{copyable_function<void(T)>{[](T){}}}; f(t);`, can the standard guarantee the value of `copies`? What if the inner one is replaced by a hand-written `struct Fwd { copyable_function<void(T)> g; void operator()(T x) { g(std::move(x)); } };`?

<details markdown="1">
<summary>Answer</summary>

In the first case it cannot: the target is a specialization of a wrapper, ¶2 allows argument aliasing, and the number of copies is unspecified.

In the second case, the outer target `Fwd` is not a wrapper specialization, and the target of the `g` called inside `Fwd` is a lambda, not a wrapper specialization either, so neither level falls under the permission in ¶2. All parameters are initialized normally according to [[expr.call]] and the equivalent code specified for each wrapper's call operator, with no uncertainty introduced by the aliasing permission.
</details>
