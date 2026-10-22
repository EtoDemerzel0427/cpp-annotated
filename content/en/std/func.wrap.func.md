---
title: Class template function
summary: "What std::function can hold, whether failing to hold something is a SFINAE-friendly failure or a hard error, why calling an empty one throws, why operator() const can modify the target, and the rules for the small-object optimization, target() and CTAD."
updated: 2026-10-19
---

!!! tldr
    - `std::function<R(Args...)>` owns a copy of its target object, and can hold any copyable object that can be called as an lvalue with a result convertible to `R`.
    - Callability is a constraint (when not met, `is_constructible` is false); copyability is Mandates (when not met, the trait is still true, and a hard error occurs only on actual construction).
    - Calling an empty `function` throws `bad_function_call`; a moved-from `function` is not guaranteed to be empty.
    - `operator()` is a const member, yet calls the target as a non-const lvalue. This const hole cannot be fixed; the new wrappers solve it with `const` in the signature.
    - Construction from a function pointer or a `reference_wrapper` is guaranteed not to throw, so `std::ref(obj)` is the standard way to hold a large object without allocating or copying.

## The problem function solves

```cpp run ok
#include <functional>
#include <cstdio>

int twice(int x) { return 2 * x; }

int main() {
    std::function<int(int)> f = twice;      // function pointer
    std::printf("%d\n", f(3));              // 6
    int k = 10;
    f = [k](int x) { return x + k; };      // lambda, a different type
    std::printf("%d\n", f(3));              // 13
    f = nullptr;                            // becomes empty
    try { f(3); } catch (const std::bad_function_call&) {
        std::puts("empty");
    }
}
```

Function pointers, lambdas and classes with `operator()` each have their own types. `std::function<int(int)>` is one fixed type that can hold any of them, as long as it can be called with an `int` and returns a value convertible to `int`. This technique of hiding the concrete type until run time is called **type erasure** ([[g:type-erasure]]).

Several terms come from [[func.def]]: a function type like `int(int)` is called a **call signature**; the callable object stored inside `function` is called the **target object**; an object that holds a target object and forwards calls to it is called a **call wrapper**. Paragraphs 1–2 of [func.wrap.func.general] say just this: `function` is a call wrapper with call signature `R(ArgTypes...)` that can store, copy and call arbitrary callable objects.

The primary template `template<class> class function;` in `<functional>` is not defined; there is only the partial specialization for function types, `function<R(ArgTypes...)>`. So `std::function<int>` is an incomplete type, and the signature cannot contain `const`, `&` or `noexcept`. For a comparison of the four wrappers, see [[func.wrap]].

## What it can hold: the converting constructor

`template<class F> function(F&& f)` decides what can be put into a `function`. Its specification is divided into several elements, each with different consequences when violated (see [[structure.specifications]] for the definitions of these elements):

¶8 Let `FD` be `decay_t<F>`, the type actually stored.

| Element | Content | When not satisfied |
|---|---|---|
| ¶9 Constraints | `F` is not `function` itself; `is_invocable_r_v<R, FD&, ArgTypes...>` | the constructor does not participate in overload resolution; `is_constructible` is false |
| ¶10 Mandates | `is_copy_constructible_v<FD>`; `is_constructible_v<FD, F>` | ill-formed, diagnostic required; but `is_constructible` is still true |
| ¶11 Preconditions | `FD` meets *Cpp17CopyConstructible* | {{ub}} |
| ¶14 Throws | does not throw when `FD` is a function pointer or a `reference_wrapper` | — |

### The constraint: called as an lvalue (¶9)

The constraint says `FD&`, not `FD`. When `function` calls its target, the target is an object inside it, called as an lvalue. So a function object with only `operator()() &&` does not satisfy the constraint.

Because this is a constraint, things that cannot be called are never treated as candidates. The two overloads below look as if they would be ambiguous, but in fact only the first is viable:

```cpp run title="overload.cpp" ok
#include <functional>
#include <string>

int g(std::function<int(int)>)         { return 1; }
int g(std::function<int(std::string)>) { return 2; }

int main() {
    return g([](int x) { return x; }) == 1 ? 0 : 1;
}
```

This lambda cannot be called with a `std::string`, so it cannot be converted to `function<int(std::string)>`, and the second `g` is excluded.

### Copyability is Mandates (¶10)

```cpp run title="move-only-target.cpp" error
#include <functional>
#include <memory>
#include <type_traits>

int main() {
    auto task = [p = std::make_unique<int>(42)] { return *p; };
    // the constraint only checks callability as an lvalue, not copyability:
    static_assert(std::is_constructible_v<std::function<int()>, decltype(task)>);
    std::function<int()> f = std::move(task);   // error: violates Mandates, the closure is not copyable
}
```

The `static_assert` passes, and the error appears in an instantiation inside the constructor. libc++ in our tests reports "call to implicitly-deleted copy constructor".

Why is it not a constraint? `function`'s copy constructor must be able to copy any target it holds. After type erasure, the code to copy the target has to be instantiated at construction, and a `function` holding a non-copyable target cannot provide that code. This is not something switching to another overload could solve, so the standard simply makes it ill-formed. To hold move-only objects, use [[func.wrap.move]].

### When the result is empty (¶12–¶13)

¶12 The following three cases construct an empty `function`: `f` is a null function pointer; `f` is a null member pointer; `f` is an empty `function` specialization of any kind. The last case does not require the same signature: constructing a `function<long()>` from an empty `function<int()>` also gives an empty one, not a wrapper holding an empty wrapper.

¶13 In the other cases, the target object is an `FD` direct-non-list-initialized ([[g:direct-non-list-initialization]]) with `std::forward<F>(f)`.

!!! pitfall "Signatures that return references reject dangling temporaries"
    Per [[func.require]], when `R` is a reference and the result of the call would need to bind to a temporary, *INVOKE*<R> is ill-formed (C++23, [[P2255R2]]). So according to the standard, `is_constructible_v<function<const int&()>, int(*)()>` should be false, and the constraint stops this dangling reference at the point of construction.

    libc++ in our tests has not caught up yet: `is_invocable_r_v<const int&, int(*)()>` is still true. `std::function<const int&()> f = []{ return 42; };` is not removed by the constraint; instead, an instantiation inside the library triggers Clang's "returning reference to local temporary object" error. It still fails to compile, but not in a SFINAE-friendly way.

## The empty state and calling

¶1–¶2 The default constructor and `function(nullptr_t)` are both `noexcept` and give an empty `function`. The `explicit operator bool()` in [func.wrap.func.cap] returns true when there is a target; because it is `explicit`, `if (f)` works but `bool b = f;` does not (see [[g:contextually-converted-to-bool]]).

[func.wrap.func.inv] specifies the call: `R operator()(ArgTypes... args) const` returns *INVOKE*<R>(f, std::forward<ArgTypes>(args)...), where `f` is the target object. When an empty `function` is called, `bad_function_call` is thrown ([[func.wrap]]). Exceptions thrown by the target propagate as usual.

The parameters are the by-value `ArgTypes...`. When the signature is `void(std::string)`, `f(s)` first copies `s` into the parameter of `operator()` and then forwards it to the target; if the target also takes it by value, that is one copy plus one move in total.

## The const hole

```cpp run title="const-hole.cpp" ok
#include <functional>
#include <cassert>

int main() {
    const std::function<int()> counter = [n = 0]() mutable { return ++n; };
    assert(counter() == 1);
    assert(counter() == 2);   // the state of a const object changed
}
```

`operator()` is a const member function, but the `f` in the call rule is the target object itself, and the standard does not require it to be called as a const lvalue. Actual implementations all call it as a non-const lvalue, so a const `function` can call a `mutable` lambda and change its captured state.

This is not just counterintuitive. The standard library promises that library functions accessing an object only through const references do not introduce data races ([[res.on.data.races]]), and much code therefore confidently calls const objects from multiple threads. A const `function` holding a stateful target, called from two threads at once, is a data race, {{ub}}, with nothing visibly wrong in the types.

This hole cannot be fixed: tightening the rule would break all existing code that holds `mutable` lambdas. [[N4159]] discusses the problem systematically. The later `move_only_function` and `copyable_function` put `const` in the signature: `copyable_function<int() const>` only accepts targets that can be called as const lvalues ([[func.wrap.move]], [[func.wrap.copy]]).

## Copying, moving and the small-object optimization

### Copying and moving (¶3–¶7)

¶3–¶4 Copy construction copies the target object. It does not throw when the target is a function pointer or a `reference_wrapper`; otherwise it may throw `bad_alloc` or whatever the target's copy constructor throws.

¶6 Move construction is `noexcept`. A moved-from `function` is in a valid but unspecified state ([[g:valid-but-unspecified-state]]) and is not guaranteed to be empty. libc++ is a counterexample:

```cpp run title="moved-from.cpp" impl
#include <functional>
#include <cstdio>

int main() {
    std::function<int()> small = [] { return 1; };
    std::function<int()> big = [a = 1L, b = 2L, c = 3L] { return int(a + b + c); };
    auto s2 = std::move(small);
    auto b2 = std::move(big);
    std::printf("small: %s\n", small ? "non-empty" : "empty");
    std::printf("big:   %s\n", big ? "non-empty" : "empty");
}
// libc++ output in our tests:
//   small: non-empty   the inline-stored target was copied over; the source keeps it
//   big:   empty       the heap target only had its pointer transferred
```

So do not check whether a `function` is empty after moving from it. To keep using it, assign a new value or `nullptr` first.

### Small-object optimization: recommendation and guarantee (¶5, ¶7, ¶14–¶15)

¶5, ¶7 and ¶15 are the same *Recommended practice*: for small targets that hold only a pointer (or reference) to an object plus a member function pointer, implementations should avoid dynamic allocation. This is a recommendation, not a requirement.

The Throws in ¶14, however, is normative: when `FD` is a function pointer or a `reference_wrapper`, construction must not throw. Not being allowed to throw `bad_alloc` means not being allowed to allocate on the heap, so for these two kinds of target, inline storage is in effect mandatory. To make a `function` use a large object without copying or allocating, the standard approach is to pass `std::ref(obj)` ([[refwrap]]), at the cost of ensuring yourself that `obj` lives long enough.

Whether other targets are stored inline is up to the implementation. The program below counts the allocations for each kind of target on libc++:

```cpp run title="sbo.cpp" impl
#include <functional>
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

int twice(int x) { return 2 * x; }

template <class F>
void probe(const char* what, F f) {
    allocs = 0;
    { std::function<int(int)> fn = f; (void)fn(1); }
    std::printf("%-22s sizeof(F)=%2zu  allocs=%d\n", what, sizeof(F), allocs);
}

int main() {
    struct Big { long a[4]; int operator()(int x) const { return x + int(a[0]); } };
    struct ThrowCopy {
        ThrowCopy() = default;
        ThrowCopy(const ThrowCopy&) noexcept(false) {}
        int operator()(int x) const { return x; }
    };
    int k = 1;
    probe("function pointer", &twice);
    probe("reference_wrapper", std::ref(twice));
    probe("lambda [&k]", [&k](int x) { return x + k; });
    probe("lambda [a,b]", [a = 1L, b = 2L](int x) { return x + int(a + b); });
    probe("lambda [a,b,c]", [a = 1L, b = 2L, c = 3L](int x) { return x + int(a + b + c); });
    probe("ThrowCopy (1 byte)", ThrowCopy{});
    probe("Big (32 bytes)", Big{});
    std::printf("sizeof(std::function<int(int)>)=%zu\n", sizeof(std::function<int(int)>));
}
// libc++ output in our tests (arm64 macOS):
//   function pointer       sizeof(F)= 8  allocs=0
//   reference_wrapper      sizeof(F)= 8  allocs=0
//   lambda [&k]            sizeof(F)= 8  allocs=0
//   lambda [a,b]           sizeof(F)=16  allocs=0
//   lambda [a,b,c]         sizeof(F)=24  allocs=1
//   ThrowCopy (1 byte)     sizeof(F)= 1  allocs=1
//   Big (32 bytes)         sizeof(F)=32  allocs=1
//   sizeof(std::function<int(int)>)=32
```

!!! impl "The libc++ implementation"
    libc++'s default `__value_func` uses the classic virtual-function scheme: a base class `__base` plus one derived class `__func<F>` per target type. A `function` object consists of an inline buffer of 3 pointers' size and a `__base*`, 32 bytes in total. `__func<F>` carries its own vtable pointer, so only 16 bytes are left for the target, and a 24-byte lambda needs an allocation.

    Inline storage also requires the target's copy constructor to be `noexcept`. When libc++ moves an inline target it actually copies it over (which is also why the moved-from `function` in the previous section is not empty), and `function`'s move constructor must be `noexcept`, so `ThrowCopy`, at only 1 byte, still has to go on the heap.

    ABI v2 (the macro `_LIBCPP_ABI_OPTIMIZED_FUNCTION`) switches to `__policy_func`: no virtual functions, but a static table of operations plus a direct call pointer. The call pointer of the empty state points to a function that throws `bad_function_call` directly, so there is no null-check branch on the path of a non-empty call.

## Assignment and destruction (¶19–¶31)

- ¶19 Copy assignment is as if by `function(f).swap(*this)`, that is, copy and then swap, giving the strong exception safety guarantee.
- ¶21 Move assignment replaces the target of `*this` with the target of `f`. The standard does not mark it `noexcept`; libc++ adds it, and [[res.on.exception.handling]] allows implementations to strengthen the exception specification of non-virtual functions.
- ¶23 `operator=(nullptr_t) noexcept` destroys the target, leaving it empty.
- ¶26–¶27 `template<class F> operator=(F&&)` has the same constraints as the converting constructor, with the effect as if by `function(std::forward<F>(f)).swap(*this)`. The Mandates on copyability takes effect indirectly through the construction of this temporary `function`.
- ¶29 `operator=(reference_wrapper<F>) noexcept` is a separate overload. Construction from a `reference_wrapper` is guaranteed not to throw, so this assignment can be marked `noexcept`. libc++ in our tests does not provide this overload; such assignments go through the general template, and `noexcept(f = std::ref(g))` is false.
- ¶31 The destructor destroys the target (if any).

The member `swap` in [func.wrap.func.mod] and the non-member `swap` in [func.wrap.func.alg] are both `noexcept` and exchange the two target objects.

## Accessing the target: target and target_type

[func.wrap.func.targ] provides two functions: `target_type()` returns `typeid(T)` (where `T` is the type of the target) when there is a target, otherwise `typeid(void)`; `target<T>()` returns a pointer to the target only when `target_type() == typeid(T)`, otherwise a null pointer. `T` must be the exact type of the target, `decay_t<F>`, not the call signature:

```cpp run title="target.cpp" ok
#include <functional>
#include <cassert>
#include <typeinfo>

int twice(int x) { return 2 * x; }

int main() {
    std::function<int(int)> f;
    assert(!f && f == nullptr && nullptr == f);

    int (*np)(int) = nullptr;
    f = np;                                        // a null function pointer gives an empty function (¶12.1)
    assert(f == nullptr);

    f = twice;
    assert(f.target_type() == typeid(int (*)(int)));
    assert(*f.target<int (*)(int)>() == &twice);
    assert(f.target<int(int)>() == nullptr);      // the signature is not the target type
    auto lam = [](int x) { return x + 1; };
    f = lam;
    assert(f.target<decltype(lam)>() != nullptr);
    assert(std::function<void()>{}.target_type() == typeid(void));
}
```

These two functions make `function` depend on RTTI ([[support.rtti]]). The standard has no mode with RTTI disabled, but `-fno-rtti` builds are common, and libc++ simply does not declare these two functions when RTTI is off. This is part of why none of the three later wrappers provide access to the target.

## Comparison with nullptr

[func.wrap.func.nullptr] declares only one `operator==(const function&, nullptr_t) noexcept`, returning `!f`. `nullptr == f` and `f != nullptr` are synthesized by C++20's rewritten candidates ([[g:rewritten-candidate]], [[over.match.oper]]); before C++20 they were separately declared overloads.

Two `function`s cannot be compared with each other. After type erasure, there is no way to tell whether two targets are equal.

## Class template argument deduction (¶16–¶18)

`function` has two deduction guides (see [[over.match.class.deduct]] for the general mechanism):

1. `function(R(*)(ArgTypes...)) -> function<R(ArgTypes...)>`, deducing from a function pointer or a function name that decays to one.
2. `template<class F> function(F) -> function<see below>`, deducing from a function object.

¶16 The second requires `&F::operator()` to be well-formed as an unevaluated operand, and its type to have one of the following three forms:

- `R(G::*)(A...) cv &opt noexceptopt`: an ordinary non-static member function; cv, `&` and `noexcept` are dropped;
- `R(*)(G, A...) noexceptopt`: an explicit object member function ([[g:explicit-object-member-function]], [[P0847R7]]), whose first parameter `G` is the object parameter and is skipped;
- `R(*)(A...) noexceptopt`: C++23's `static operator()` ([[P1169R4]]).

¶17 The deduced type is `function<R(A...)>`.

```cpp run title="ctad.cpp" ok
#include <functional>
#include <type_traits>

int add(int a, int b) { return a + b; }

struct T {
    static char operator()(int) { return 'x'; }     // static operator() (C++23)
};

int main() {
    std::function f1 = add;                          // guide 1
    std::function f2 = [](double) { return 1; };     // guide 2
    std::function f3 = T{};
    static_assert(std::is_same_v<decltype(f1), std::function<int(int, int)>>);
    static_assert(std::is_same_v<decltype(f2), std::function<int(double)>>);
    static_assert(std::is_same_v<decltype(f3), std::function<char(int)>>);
    auto ne = [](int) noexcept { return 0; };
    std::function f4 = ne;                           // noexcept is dropped
    static_assert(std::is_same_v<decltype(f4), std::function<int(int)>>);
}
```

`&F::operator()` must be unique and not a template. The `operator()` of a generic lambda is a template whose address cannot be taken, so the second guide is unusable:

```cpp run title="ctad-generic.cpp" error
#include <functional>

int main() {
    std::function g = [](auto x) { return x; };   // error: no usable deduction guide
}
```

Likewise, classes with several `operator()` overloads and the results of `std::bind` cannot use CTAD. Note 1 in [func.wrap.func.general] also warns that the types deduced by the deduction guides may change in the future, so do not rely on the exact result.

!!! impl "libc++ does not implement the explicit object parameter form yet"
    By the second form, `struct S { long operator()(this S, double); };` should deduce `function<long(double)>`. libc++ in our tests treats the explicit object parameter as an ordinary parameter and deduces `function<long(S, double)>`, so `std::function f = S{};` fails to compile ("no viable conversion from 'S' to 'std::function<long (S, double)>'"). This is a libc++ defect.

## Questions

!!! question "Question 1"
    If `std::is_constructible_v<std::function<void()>, F>` is true, is `std::function<void()> f = F{};` guaranteed to compile? What about the converse?

<details markdown="1">
<summary>Answer</summary>

No. The trait reflects only the constraints (¶9): `F` is not `function` itself, and `decay_t<F>` can be called as an lvalue. Copyability belongs to Mandates (¶10), which does not affect the trait, and violating it is a hard error. A closure capturing a `unique_ptr` makes the trait true while construction fails.

Conversely, a false trait means the converting constructor does not participate in overload resolution. The remaining candidates are only the copy, move and `nullptr_t` constructors, `F` cannot be converted to their parameter types, so construction is guaranteed to fail.
</details>

!!! question "Question 2"
    When the argument is `std::ref(g)`, why is `operator=(reference_wrapper<F>)` selected rather than the general `template<class F> operator=(F&&)`?

<details markdown="1">
<summary>Answer</summary>

Both are function templates, and the argument type matches both exactly, so the implicit conversion sequences are indistinguishable, and the decision falls to partial ordering of function templates ([[temp.deduct.partial]]). A `reference_wrapper<F>` can be used as an argument to deduce the `F&&` parameter, but not the other way round, so the `reference_wrapper<F>` version is more specialized and is selected. This version can be declared `noexcept` because ¶14 guarantees that construction from a `reference_wrapper` does not throw.
</details>

!!! question "Question 3"
    `const std::function<void()> f = [v = std::vector<int>{}]() mutable { v.push_back(1); };` is called from two threads at the same time. Who is to blame for the UB?

<details markdown="1">
<summary>Answer</summary>

Two threads modifying the same `vector` (the closure's captured member) at the same time is a data race ([[intro.races]]), which is UB. [[res.on.data.races]] constrains the standard library not to introduce data races itself; here the modification is done by the user-provided target object, and the standard library merely called it via *INVOKE*, so the responsibility lies with the user. With `copyable_function<void() const>` instead, this `mutable` lambda could not be held at all.
</details>
