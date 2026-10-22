---
title: "Non-owning wrapper: function_ref"
summary: "C++26's function_ref stores only a pointer to a callable object and a call function pointer; it never allocates, is trivially copyable and has no empty state. It is well suited to function parameters and dangles easily when used as a variable."
updated: 2026-10-19
---

!!! tldr
    - `function_ref` is a reference to a callable object, much as `string_view` is to a string: it does not own the target, is two pointers wide, trivially copyable, never allocates, and is freestanding.
    - It stores the target's address. As a function parameter it is safe; initialize a `function_ref` variable with a temporary and it dangles at the semicolon, captureless lambdas included.
    - There is no default constructor, no empty state, and no `operator bool`.
    - A function known at compile time is passed with `std::cw<f>`; a member function can be bound to an object with `{std::cw<&C::mf>, obj}`, and binding an rvalue object is rejected by a constraint.
    - Except for function pointers, `constant_wrapper` and compatible `function_ref`s, assigning to it is always a deleted operation, to avoid creating references that are certain to dangle.

!!! warning "Implementation status"
    libc++ (LLVM 23) in our tests does not implement `function_ref` yet; `__cpp_lib_function_ref` in `<version>` is commented out. The `constant_wrapper` it depends on ([[const.wrap.class]]) is already provided. The `function_ref` examples on this page cannot be compiled with this setup, so they carry no verdict tags.

## Why it is needed

```cpp run title="fr-param.cpp"
#include <functional>

void repeat(int times, std::function_ref<void(int)> fn) {
    for (int i = 0; i < times; ++i) fn(i);
}

int main() {
    int sum = 0;
    repeat(4, [&sum](int i) { sum += i; });   // no allocation, no copy of the lambda
    return sum == 6 ? 0 : 1;
}
```

The most common use of callbacks needs no ownership: a function takes a callback, calls it some number of times before returning, and then no longer needs it. Constructing a `std::function` for this may require a heap allocation and copying the target; writing it as a template drags the implementation into the header.

`function_ref` ({{c++26}}, [[P0792R14]]) only remembers where the target is and how to call it; the target's lifetime is the caller's responsibility. It needs no heap, exceptions or RTTI, so it is marked freestanding in `<functional>` and can be used even on bare metal.

## The signature: only const and noexcept

[func.wrap.ref.general] specifies partial specializations of the form `function_ref<R(ArgTypes...) cv noexcept(noex)>`: *cv* is `const` or empty, *noex* is true or false, 4 combinations in total. There is no ref-qualifier in the signature, because `function_ref` never owns its target, and ownership semantics such as calling the target as an rvalue and hollowing it out make no sense here.

*cv* determines how the target is called: `function_ref<void() const>` calls the target as a const lvalue, and `function_ref<void()>` calls it as a non-const lvalue. The wrapper's `operator()` is always const. A `function_ref` is a reference, and calling it does not change the reference itself, just as `T* const p` can still modify `*p`. Whether the target can be modified is stated explicitly by the *cv* in the signature, so there is no const hole here like the one in `std::function` ([[func.wrap.func]]).

## Internal representation ([func.wrap.ref.class])

Paragraph 1 describes two exposition-only members:

- *bound-entity* ([[g:bound-entity]]): an object of an unspecified trivially copyable type that models `copyable` and can hold an object pointer or a function pointer.
- *thunk-ptr* ([[g:thunk-ptr]]): a function pointer of type `R(*)(BoundEntityType, ArgTypes&&...) noexcept(noex)`.

A call ([func.wrap.ref.inv]) executes `return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`. The thunk is a small function generated at construction for the concrete target type, which knows how to turn *bound-entity* back into the target and call it. The whole type erasure is a data pointer plus a function pointer, with no vtable needed, because `function_ref` never copies, moves or destroys its target.

The *call-args* defined in paragraph 3 is an argument pack for which `decltype((call-args))...` is exactly `ArgTypes&&...`. The thunk's parameters are all references, so the by-value `ArgTypes...` parameters of a `function_ref` call are constructed only once and then passed to the thunk by reference.

### Trivially copyable

!!! std
    Each specialization of function_ref is a trivially copyable type ([basic.types.general]) that models copyable.

This is not just about copies being cheap; it also determines how arguments are passed. On platforms that use the Itanium C++ ABI, such as Linux and macOS, a class with a non-trivial copy constructor, move constructor or destructor must be constructed as a temporary in memory and passed by address; other classes are passed according to the rules for C structs. On x86-64 System V and AArch64, a struct of two pointers' size goes in two registers, so passing the parameter of `void f(function_ref<void()>)` is exactly the same as passing a C-style callback `(void* ctx, void (*fn)(void*))`.

The defaulted copy constructor and copy assignment operator in the class synopsis, together with trivial members, satisfy the conditions for being trivially copyable ([[class.prop]]).

`function_ref` has no default constructor and therefore no empty state: no `operator bool`, and no comparison with `nullptr`. Every `function_ref` refers to some callable entity.

## Constructors ([func.wrap.ref.ctor])

¶1 The exposition-only predicate *is-invocable-using*<T...> is just `is_invocable_r_v<R, T..., ArgTypes...>`, replaced by the nothrow version when *noex* is true.

### From a function pointer (¶3–¶5)

`template<class F> function_ref(F* f) noexcept;`

- ¶3 Constraints: `F` is a function type, and *is-invocable-using*<F>.
- ¶4 Preconditions: `f` is not a null pointer. `function_ref` has no empty state to fall back to, so a violation is {{ub}}.
- ¶5 *bound-entity* stores `f`, and the thunk calls `invoke_r<R>(f, call-args...)`.

This is the only constructor that is not `constexpr`.

### From any callable object (¶6–¶9)

`template<class F> constexpr function_ref(F&& f) noexcept;`, where ¶6 lets `T` be `remove_reference_t<F>`.

¶7 Constraints: `F`, with cv and references removed, is not `function_ref` itself (the same specialization goes to the copy constructor); `T` is not a member pointer; *is-invocable-using*<cv T&>. Member pointers are excluded because a member pointer is itself just a value that `function_ref` has nowhere to point to long-term; to bind a member function, use the `constant_wrapper` constructors below.

¶8 In the general case, *bound-entity* stores `addressof(f)`, and the thunk calls the target as `static_cast<cv T&>(f)`. Whether `f` is an lvalue or an rvalue, what is stored is its address; all the dangling problems below stem from this.

Paragraphs 2 and 8 also handle a special case: `F` is another `function_ref` with exactly the same return type and parameters as this type, differing only in cv or `noexcept`, and the conversion goes in the safe direction (`noexcept` can become non-`noexcept`; a source with a non-const signature cannot convert to a const signature). In that case the other one's *bound-entity* and *thunk-ptr* are copied directly, instead of referring to that `function_ref` object. This is a normative requirement.

¶9 goes further and allows that, as long as `F` is any `function_ref` specialization (the signature may differ, for example a parameter changing from `std::string` to `std::string&&`), the implementation may also copy its two pointers directly. The standard's example shows the consequence:

```cpp
void f1(std::string);
void f2(std::string);

function_ref<void(std::string)> r1(&f1);
function_ref<void(std::string&&)> r2(r1);   // refer to r1, or copy r1's state?
r2("");                                      // calls f1
r1 = &f2;
r2("");                                      // unspecified whether f1 or f2 is called
```

If `r2` refers to the object `r1`, then after `r1` is reassigned `r2` calls `f2`; if it copied the state, it still calls `f1`. The standard makes this unspecified behavior ({{unspec}}), in exchange for the freedom of implementations to avoid double wrapping ([[func.wrap]] paragraph 3).

### From constant_wrapper (¶10–¶20)

When the function to be called is known at compile time, there is no need to store its address at run time. Three constructors accept a `constant_wrapper<c, F>`, usually written `std::cw<f>` ([[const.wrap.class]]):

| Form | *bound-entity* | The thunk is equivalent to |
|---|---|---|
| `function_ref(cw<f>)` (¶10–¶12) | no object bound | `invoke_r<R>(f.value, call-args...)` |
| `function_ref(cw<f>, obj)` (¶13–¶16) | `addressof(obj)` | `invoke_r<R>(f.value, static_cast<cv T&>(obj), call-args...)` |
| `function_ref(cw<f>, ptr)` (¶17–¶20) | `ptr` | `invoke_r<R>(f.value, ptr, call-args...)` |

In the first case the function is a template argument, the thunk calls it directly, and the compiler can inline it into the thunk, saving an indirect call through a function pointer. The latter two are for binding a member function to an object and can replace `std::bind` or a lambda:

```cpp run title="fr-member.cpp"
#include <functional>
#include <utility>

struct Counter {
    int n = 0;
    void add(int k) { n += k; }
};

void repeat(int times, std::function_ref<void(int)> fn) {
    for (int i = 0; i < times; ++i) fn(i);
}

int main() {
    Counter c;
    repeat(4, {std::cw<&Counter::add>, c});     // bound to the object c
    repeat(4, {std::cw<&Counter::add>, &c});    // bound to a pointer
    // repeat(4, {std::cw<&Counter::add>, Counter{}});   // error: the constraint rejects rvalue objects (¶14.1)
    return c.n == 12 ? 0 : 1;
}
```

- ¶14.1 The constraint requires `obj` not to be an rvalue. Binding a temporary is almost certain to dangle, so it is rejected outright.
- ¶11.1, ¶15, ¶18 Mandates: when `f.value` is a pointer or a member pointer, it cannot be null. The value is a compile-time constant, so it can be checked at compile time.
- ¶19 Preconditions: when a member pointer is paired with an object pointer, the object pointer cannot be null. This is a run-time value, so it can only be a precondition.

!!! history "nontype and constant_wrapper"
    [[P0792R14]] originally used a dedicated tag type `std::nontype_t<f>` (written `std::nontype<f>`) for this group of constructors. Before C++26 was finalized, [[P3774R1]] removed `nontype` in favor of the more general `std::constant_wrapper`. The `std::nontype<&Counter::add>` in earlier articles and implementations means the same as today's `std::cw<&Counter::add>`.

### Deleted assignment (¶21)

```cpp
template<class T> function_ref& operator=(T) = delete;
```

¶21 Constraints: `T` is not a convertible `function_ref` specialization, not a pointer, and not a `constant_wrapper` specialization. Apart from these three categories, assigning anything else to a `function_ref` selects this deleted function, the most typical case being a lambda:

```cpp
std::function_ref<int()> r = &some_function;
r = &other_function;          // OK: not caught by the deletion; implicit conversion, then copy assignment
r = std::cw<other_function>;  // OK
r = [] { return 1; };         // error: selects the deleted operator=(T)
```

Without this deletion, `r = [] { return 1; };` would first construct a temporary `function_ref` from the temporary lambda and then copy-assign it. The lambda is destroyed at the end of the statement, and `r` dangles immediately. The deleted assignment turns this certain-to-dangle code into a compile error. Function pointers are never destroyed and `cw` binds no object, so these two categories are let through.

## Invocation

[func.wrap.ref.inv]: `R operator()(ArgTypes... args) const noexcept(noex);` is equivalent to `return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`. It has no precondition, because there is no empty state. But if the referenced object has already been destroyed, the thunk accesses an object whose lifetime has ended, which is {{ub}} ([[basic.life]]).

## Lifetime: safe as a parameter, dangerous as a variable

```cpp run title="fr-lifetime.cpp"
#include <functional>

int apply(std::function_ref<int(int)> f, int x) { return f(x); }

int main() {
    int k = 10;
    int a = apply([k](int x) { return x + k; }, 1);   // OK

    std::function_ref<int(int)> r = [k](int x) { return x + k; };
    int b = r(1);                                       // UB: the closure object was destroyed at the end of the previous line

    auto lam = [k](int x) { return x + k; };
    std::function_ref<int(int)> r2 = lam;               // OK: lam outlives r2
    return a + b + r2(1);
}
```

The first case is safe, because a temporary is not destroyed until the end of the full-expression ([[class.temporary]]), and the whole call to `apply` is within that full-expression. In the second case, the initialization of `r` is a separate full-expression; the closure is destroyed at the semicolon, and the address stored in `r` dangles immediately.

!!! pitfall "Captureless lambdas dangle too"
    `std::function_ref<int()> r = [] { return 42; };` looks harmless, since a captureless lambda can be converted to a function pointer. But template argument deduction does not consider user-defined conversions, so `function_ref(F*)` cannot deduce `F` from the closure type; `function_ref(F&&)` is selected, and what is stored is still the address of the temporary closure object. Two fixes:

    - Convert to a function pointer first with unary `+`: `function_ref<int()> r = +[] { return 42; };`
    - Use `constant_wrapper`: `function_ref<int()> r = std::cw<[] { return 42; }>;`. The closure type of a captureless lambda can be used as a constant template argument.

!!! pitfall "Referring to an owning wrapper"
    `function_ref<void()> r = some_move_only_function;` refers to that `move_only_function` object itself; it is not a `function_ref`, so the state-copying branch of ¶8 does not apply. If that object is later moved from, reassigned or destroyed, `r`'s behavior changes accordingly or dangles. Initializing a `function_ref` variable with a `std::function` temporary returned from a function dangles in the same way.

So `function_ref` is not suitable as a data member or a container element, unless you can be sure the referenced object outlives the holder. For callbacks that need to be stored, use [[func.wrap.move]] or [[func.wrap.copy]].

## Deduction guides ([func.wrap.ref.deduct])

| Guide | Constraint | Deduced |
|---|---|---|
| `function_ref(F*)` | `F` is a function type (paragraph 1) | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F0>)` | `F`, that is `remove_pointer_t<F0>`, is a function type (paragraphs 2–4) | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F>, T&&)` | see below (paragraphs 5–6) | `function_ref<R(A...) noexcept(E)>` |

The third is distinguished by the form of `F`:

- `F` is a pointer to member function `R(G::*)(A...) cv &opt noexcept(E)`: the object is bound, and the remaining parameters are `A...`;
- `F` is a pointer to data member `M G::*`: `R` is `invoke_result_t<F, T&>`, that is, a reference to the member, there are no parameters, and `E` is true;
- `F` is a function pointer `R(*)(G, A...) noexcept(E)`: the first parameter is bound as the object.

There is no guide for deducing from an arbitrary function object, so `std::function_ref r = lambda;` is ill-formed. The deduced signatures also never carry `const`; the third guide drops the *cv* of a member function.

```cpp run title="fr-deduce.cpp"
#include <functional>
#include <type_traits>
#include <utility>

int twice(int x) noexcept { return 2 * x; }
struct P { int x; int get() const { return x; } };

int main() {
    std::function_ref a = &twice;                  // function_ref<int(int) noexcept>
    std::function_ref b = std::cw<twice>;          // function_ref<int(int) noexcept>
    P p{3};
    std::function_ref c{std::cw<&P::get>, p};      // function_ref<int()>, const dropped
    std::function_ref d{std::cw<&P::x>, p};        // function_ref<int&() noexcept>
    static_assert(std::is_same_v<decltype(c), std::function_ref<int()>>);
    static_assert(std::is_same_v<decltype(d), std::function_ref<int&() noexcept>>);
    return a(1) + b(1) + c() + d() == 10 ? 0 : 1;
}
```

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶11.2 is a Mandates: if `ArgTypes` is non-empty, all of them, with cv and references removed, model *constexpr-param* (that is, are themselves types like `constant_wrapper`), and `constant_wrapper<INVOKE(f.value, remove_cvref_t<ArgTypes>::value...)>` is a valid type, then the program is ill-formed. The reason is that in this situation `constant_wrapper`'s own `operator()` would evaluate at compile time and return a new `constant_wrapper` ([[const.wrap.class]]), whereas the `function_ref` thunk calls `f.value` at run time. The same spelling would have two meanings, and the standard chooses to reject it outright.

¶2 encodes *is-convertible-from-specialization* with two `is_convertible_v`s: the `noexcept` direction uses the convertibility of the function reference `R(&)(Args...) noexcept(noex2)` to `R(&)(Args...) noexcept(noex)`, and the cv direction uses the convertibility of `int cv&` to `int cv2&`.

</details>

## Questions

!!! question "Question 1"
    Which of these lines dangles?
    ```cpp
    std::move_only_function<int()> make();
    void use(std::function_ref<int()>);

    use(make());                                   // (1)
    std::function_ref<int()> r1 = make();          // (2)
    auto m = make();
    std::function_ref<int()> r2 = m;               // (3)
    ```

<details markdown="1">
<summary>Answer</summary>

- (1) Safe: the temporary returned by `make()` lives until the end of the full-expression, and `use` completes its call within that time.
- (2) Dangles: `r1` stores the address of the temporary `move_only_function` (¶8), the temporary is destroyed at the semicolon, and calling `r1()` afterwards is UB. The single-argument constructor places no restriction on rvalues, intentionally, since otherwise correct uses like (1) would also be rejected. Only the `constant_wrapper`-plus-object constructors reject rvalues (¶14.1).
- (3) Safe, provided `m` outlives `r2`. If `m` is later reassigned, `r2` calls the new target, because it refers to the object `m`.
</details>

!!! question "Question 2"
    Why can the `operator()` of `function_ref` be const without having `std::function`'s const hole?

<details markdown="1">
<summary>Answer</summary>

`std::function` owns its target, the target is part of the wrapper, and a const wrapper ought to mean a const target, yet it calls the target in a non-const way. `function_ref` does not own its target; it is a reference: the reference itself being const is a separate matter from whether the referenced object can be modified. The latter is stated explicitly by the *cv* of the signature: `function_ref<void()>` declares that it calls the target as a non-const lvalue, and `function_ref<void() const>` only accepts targets that can be called in a const way. The type describes the behavior truthfully, so there is no hole.
</details>
