---
title: "Requirements: INVOKE and call wrappers"
summary: "Everywhere the standard library needs to call a callable, it comes down to the seven-bullet definition of INVOKE(f, t1, …, tN). This page covers it, its return-type version INVOKE<R>, std::invoke / invoke_r, and the layers of call wrapper concepts that bind, bind_front, not_fn and mem_fn rely on."
updated: 2026-10-19
---

!!! tldr
    - A member pointer cannot be called as `f(obj)`. *INVOKE* unifies pointers to member functions, pointers to data members and ordinary callables into a single kind of call, and `std::invoke`, `function`, `bind`, `is_invocable` and others are all specified in terms of it.
    - *INVOKE* tries seven bullets in order: the object itself, `reference_wrapper`, and otherwise dereference `*t1`; a pointer to data member takes exactly one argument. A bullet is chosen by type alone; once chosen, if the expression is invalid it is invalid, and there is no fallback to the next bullet.
    - *INVOKE*&lt;R&gt; implicitly converts the result to `R`, and discards it when `R` is `void`. Since C++23, it is ill-formed if the conversion would bind a reference to a temporary.
    - Call wrappers come in layers: argument forwarding (`bind`), perfect forwarding (`bind_front`, `not_fn`, which also forward the stored state according to the wrapper's value category), and simple (`mem_fn`, unconditionally copyable).
    - A perfect forwarding call wrapper is expression-equivalent to its call pattern: when some overload of the target object is deleted, the wrapper must not quietly use a different overload instead.

## Why *INVOKE* is needed

```cpp
struct Widget { int id; void draw() const; };
void free_draw(const Widget&);

Widget w; Widget* p = &w;
free_draw(w);          // ordinary function: f(args...)
(w.*&Widget::draw)();  // pointer to member function: (obj.*pmf)(args...)
(p->*&Widget::draw)(); // through a pointer: (ptr->*pmf)(args...)
w.*&Widget::id;        // pointer to data member: obj.*pmd
```

The things that can be called in C++ are not written uniformly. Functions, function pointers and lambdas use `f(args...)`; member pointers must be written as `(obj.*pmf)(args...)` or `obj.*pmd` ([[expr.mptr.oper]]), and the object side may also be a pointer, a smart pointer or a `reference_wrapper`.

To deal with this, the standard defines an exposition-only pseudo-function ***INVOKE*(f, t1, …, tN)** that unifies all these cases into a single form. `std::invoke`, `reference_wrapper::operator()`, `bind`, `bind_front`, `not_fn`, `mem_fn`, `function`, `move_only_function`, `is_invocable` and `invoke_result` in `<type_traits>`, `std::apply`, `std::visit`, `std::thread`, and the projections of ranges algorithms all have their specifications ultimately written as "returns *INVOKE*(…)".

## Terminology [func.def]

A **call signature** ([[g:call-signature]]) is the name of a return type followed by a parenthesized list of argument types, such as `int(double, char)`. The template argument of `std::function<R(Args...)>` is a call signature.

A **callable type** ([[g:callable-type]]) is a function object type or a pointer-to-member type. A function object type is an object type that can appear in the postfix-expression position of a function call ([[function.objects]]). A member pointer is not a function object type, and `pmf(obj)` is not a valid expression, but it is a callable type. An object of callable type is called a **callable object**.

A **call wrapper type** ([[g:call-wrapper]]) holds a **target object** ([[g:target-object]]) and provides a call operation that forwards to it. The target object is a callable object, or an object that represents a callable object: a `reference_wrapper` stores a pointer, but what it represents is the referenced callable. An object of a call wrapper type is called a **call wrapper**.

A call wrapper can also store a sequence of objects and references to be passed along as arguments to the target when it is called; these are collectively called **bound argument entities** ([[g:bound-argument-entities]]), for example the `1` and `2` in `bind_front(f, 1, 2)`. The target object and the bound argument entities together are called the **state entities** ([[g:state-entities]]).

## The seven bullets of *INVOKE* [func.require]

```cpp run title="invoke_bullets.cpp" ok
#include <functional>
#include <memory>
#include <utility>
#include <type_traits>
#include <cstdio>
struct Base { int v = 1; int get() const { return v; } };
struct Derived : Base {};
int main() {
  Derived d;
  std::unique_ptr<Base> up = std::make_unique<Base>();
  auto pmf = &Base::get;
  auto pmd = &Base::v;
  std::printf("%d\n", std::invoke(pmf, d));             // ¶1.1 d.*pmf, Derived derives from Base
  std::printf("%d\n", std::invoke(pmf, std::ref(d)));   // ¶1.2 d.get().*pmf
  std::printf("%d\n", std::invoke(pmf, &d));            // ¶1.3 (*&d).*pmf
  std::printf("%d\n", std::invoke(pmf, up));            // ¶1.3 (*up).*pmf
  std::invoke(pmd, d) = 42;                             // ¶1.4 lvalue object, gives int&
  std::printf("%d\n", d.v);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, Derived{})), int&&>);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, &d)), int&>);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, std::as_const(d))), const int&>);
}
```

¶1 *INVOKE*(f, t1, t2, …, tN) tries the following seven bullets in order. The first three handle pointers to member functions, the next three handle pointers to data members, and the last handles everything else. In the table, `U` is `remove_cvref_t<decltype(t1)>` and `T` is the class the member pointer belongs to:

| Bullet | f is | Condition | Expands to |
|---|---|---|---|
| ¶1.1 | a pointer to member function of `T` | `U` is `T` or derived from `T` | `(t1.*f)(t2, …, tN)` |
| ¶1.2 | same | `U` is a specialization of `reference_wrapper` | `(t1.get().*f)(t2, …, tN)` |
| ¶1.3 | same | neither of the above | `((*t1).*f)(t2, …, tN)` |
| ¶1.4 | a pointer to data member of `T`, and N = 1 | `U` is `T` or derived from `T` | `t1.*f` |
| ¶1.5 | same | `U` is a specialization of `reference_wrapper` | `t1.get().*f` |
| ¶1.6 | same | neither of the above | `(*t1).*f` |
| ¶1.7 | all other cases | | `f(t1, t2, …, tN)` |

A few details:

- The third bullet only requires `*t1` to be valid. Raw pointers, `unique_ptr`, `shared_ptr`, iterators, even `optional`, all go through ¶1.3 or ¶1.6. There is no constraint that it be a pointer.
- The value category propagates from `t1`. ¶1.1 and ¶1.4 write `t1.*f` directly, so taking a data member from an rvalue object gives an xvalue (`int&&`), a `const` lvalue gives `const int&`, and calling a member function on an rvalue object selects the `&&`-qualified overload. Via ¶1.6, `*t1` is generally an lvalue, so access through a pointer always gives an lvalue. `t1.get()` is also always an lvalue, so a `&&`-qualified member function cannot be called through a `reference_wrapper`.
- A pointer to data member takes exactly one argument. With extra arguments, the premise N = 1 of ¶1.4–¶1.6 does not hold, so it falls to ¶1.7's `f(t1, t2)`, and a member pointer cannot be called that way, so it is ill-formed.
- ¶1.7 is an ordinary function call. It covers functions, function references, function pointers, classes with `operator()`, and classes implicitly convertible to function pointers (via a surrogate call function; see [[over.call.object]]).

### Bullets are chosen by type alone

¶1.1 and ¶1.4 use `is_base_of_v` to test derivation, and `is_base_of_v` is also true for private and ambiguous bases. So when `D` privately inherits from `B`, `INVOKE(&B::v, d)` selects ¶1.4 and expands to `d.*(&B::v)`, which is ill-formed because access checking fails. It does not step back to try ¶1.6's `(*d).*f`.

```cpp run title="invoke_edges.cpp" ok
#include <functional>
#include <type_traits>
struct S { void f() && {} };
static_assert(std::is_invocable_v<decltype(&S::f), S>);    // rvalue t1: selects the &&-qualified member
static_assert(!std::is_invocable_v<decltype(&S::f), S&>);  // lvalue t1: not allowed

struct B { int v; };
struct D : private B {};
static_assert(!std::is_invocable_v<int B::*, D&>);         // selects ¶1.4, access fails; no fallback to ¶1.6
static_assert(!std::is_invocable_v<int B::*, B&, int>);    // extra argument: falls to ¶1.7, ill-formed
int main() {}
```

!!! ub "Null member pointers and null object pointers"
    *INVOKE* does not check the values of `f` and `t1`. When `f` is a null member pointer, `t1.*f` is undefined behavior ([[expr.mptr.oper]]); via ¶1.3 with `t1` a null pointer, `*t1` is undefined behavior too. `std::invoke` does not check for you.

## *INVOKE*&lt;R&gt;: specifying the return type

Many components know what type the result of the call must become. When `std::function<long(int)>` wraps a function returning `int`, the result must be converted to `long`; when `std::function<void()>` wraps the same function, the result is simply discarded.

¶2 *INVOKE*&lt;R&gt;(f, t1, …, tN) is defined for this purpose:

- When `R` is cv `void`, it is `static_cast<void>(INVOKE(f, t1, …, tN))`, and the result is discarded. The explicit conversion to `void` also suppresses `[[nodiscard]]` warnings.
- Otherwise, it is *INVOKE*(f, t1, …, tN) implicitly converted to `R`. Implicit conversion amounts to copy-initialization; `explicit` conversion functions do not count, consistent with `is_convertible`.

### No binding references to temporaries (C++23)

```cpp
std::function<const int&()> f = [] { return 42; };
const int& r = f();   // C++20: compiles, r dangles
                      // since C++23: the construction of f is rejected
```

The lambda returns an `int` prvalue. To convert it to `const int&`, a temporary `int` must first be materialized, and that temporary is destroyed as soon as `f()` returns. Since C++23, the last sentence of ¶2 says ([[P2255R2]]):

!!! std
    If reference_converts_from_temporary_v&lt;R, decltype(*INVOKE*(f, t1, t2, …, tN))&gt; is true, *INVOKE*&lt;R&gt;(f, t1, t2, …, tN) is ill-formed.

`reference_converts_from_temporary_v<R, X>` is true when `R` is a reference type and initializing `R` with an expression of type `X` would bind it to a temporary ([[meta]]). `is_invocable_r` is defined in terms of whether *INVOKE*&lt;R&gt; is well-formed, so according to the standard `is_invocable_r_v<const int&, int(*)()>` is false, and both the constructor constraints of `function` ([[func.wrap.func]]) and `invoke_r` reject this combination.

This rule only concerns references. `is_invocable_r_v<std::string_view, std::string(*)()>` is still true, even though the resulting `string_view` points into a temporary `string` that is about to be destroyed.

!!! impl "libc++ does not implement this constraint yet"
    In libc++ (LLVM 23) in our tests, `is_invocable_r_v<const int&, int(*)()>` is still true; `invoke_r` in `__functional/invoke.h` still carries the comment `TODO: Use reference_converts_from_temporary_v once implemented`.

    `std::invoke_r<const int&>(f)` is in fact still rejected, but for a core-language reason: since C++26, a `return` statement that binds the returned reference to a temporary is ill-formed ([[stmt.return#6]]). Clang reports "returning reference to local temporary object", with the error located inside libc++'s `invoke_r` function body. The standard requires an unsatisfied constraint, i.e. not participating in overload resolution; libc++ gives a hard error in the function body. The earlier `std::function<const int&()>` example is also rejected in our tests, for the same reason.

```cpp run title="invoke_r_dangling.cpp" error
#include <functional>
int f() { return 42; }
const int& r = std::invoke_r<const int&>(f);   // error: INVOKE<const int&> is ill-formed
int main() {}
```

## `std::invoke` and `std::invoke_r` [func.invoke]

```cpp
template<class F, class... Args>
  constexpr invoke_result_t<F, Args...> invoke(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_v<F, Args...>);
template<class R, class F, class... Args>
  constexpr R invoke_r(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_r_v<R, F, Args...>);
```

These two functions turn *INVOKE* and *INVOKE*&lt;R&gt; into functions that can be called directly, perfectly forwarding the arguments as they are (paragraphs 2 and 4). Their constraints are `is_invocable_v<F, Args...>` and `is_invocable_r_v<R, F, Args...>` respectively (paragraphs 1 and 3). When the call is not possible they do not participate in overload resolution, so they can be probed in a `requires` expression.

`<type_traits>` answers whether it can be called, what the result type is and whether it can throw; `std::invoke` actually makes the call; both sides use the same definition of *INVOKE*. The return type `invoke_result_t<F, Args...>` is just the `decltype` of the *INVOKE* expression, preserving the value category, so `invoke(pmd, std::move(obj))` returns `int&&`. The `noexcept` condition comes from `is_nothrow_invocable`.

`invoke` was added in C++17 and has been `constexpr` since C++20 ([[P1065R2]]). `invoke_r` was added in C++23 ([[P2136R3]]) and was `constexpr` from the start. Both must also be provided in freestanding implementations.

```cpp run title="constexpr_invoke.cpp" ok
#include <functional>
struct Emp { int id; double salary; };
constexpr int sq(int x) { return x * x; }
static_assert(std::invoke(sq, 5) == 25);                     // constexpr since C++20
static_assert(std::invoke(&Emp::id, Emp{3, 1.0}) == 3);      // pointer to data member
static_assert(std::invoke_r<long>(sq, 3) == 9L);             // result implicitly converted to long
int main() {}
```

## The layers of call wrappers

The specifications of `bind`, `bind_front`, `not_fn` and `mem_fn` only say which layer of call wrapper they return and what the call pattern is; the actual semantics are all in ¶3–¶8.

| Layer | Additional requirements | Examples in the standard library |
|---|---|---|
| call wrapper | move-constructible, destructible | all |
| argument forwarding call wrapper | call arguments forwarded as references | `bind` |
| perfect forwarding call wrapper | state entities also forwarded according to the wrapper's value category and const | `bind_front`, `bind_back`, `not_fn` |
| simple call wrapper | unconditionally copyable and assignable, with the relevant operations `constexpr` and non-throwing | `mem_fn` |

### Argument forwarding call wrappers (¶3)

¶3 Every call wrapper meets *Cpp17MoveConstructible* and *Cpp17Destructible*. Whether it is copyable depends on its state entities (see ¶7).

An **argument forwarding call wrapper** ([[g:argument-forwarding-call-wrapper]]) can accept an arbitrary argument list and passes the arguments to the target as references: rvalue arguments as rvalue references, lvalue arguments as lvalue references. Note 1 says that a typical implementation is a call operator of the form `template<class... UnBoundArgs> R operator()(UnBoundArgs&&...) cv-qual;` whose parameters are forwarding references ([[g:forwarding-reference]]).

The result of `std::bind` belongs to this layer. The arguments passed at the call are perfectly forwarded, while the bound function and bound arguments are always handed over as lvalues; see [[func.bind]] for details.

### Perfect forwarding call wrappers and call patterns (¶4, ¶5)

¶4 A **perfect forwarding call wrapper** ([[g:perfect-forwarding-call-wrapper]]) goes beyond argument forwarding and forwards the state entities too. When the wrapper is called as an lvalue, a state entity of type `T` is handed over as `cv T&`, otherwise as `cv T&&`, where `cv` is the cv-qualification of the wrapper itself and cannot include `volatile`.

¶5 A **call pattern** ([[g:call-pattern]]) specifies the semantics of calling a perfect forwarding call wrapper. A postfix call on the wrapper is [[g:expression-equivalent|expression-equivalent]] to the expression obtained by replacing the arguments and state entities in the call pattern with the references described above. For example, the call pattern of `bind_front` is `invoke(fd, bound_args..., call_args...)` ([[func.bind.partial]]), so for `auto g = std::bind_front(f, a);`:

- `g(x)` is equivalent to `invoke(static_cast<FD&>(fd), static_cast<BoundArgs&>(bound_args)..., x)`;
- `std::move(g)(x)` is equivalent to the version with `FD&&` and `BoundArgs&&`;
- `std::as_const(g)(x)` is equivalent to the version with `const FD&` and `const BoundArgs&`.

Expression-equivalence requires the two expressions to be both well-formed or both ill-formed, to have the same `noexcept`-ness, to be constant subexpressions or not alike, and to have the same effects. An easily overlooked conclusion follows:

```cpp run title="no_fallback.cpp" error
#include <functional>
struct F {
  void operator()() const {}
  void operator()() = delete;
};
int main() {
  auto g = std::bind_front(F{});
  g();   // error: fd is F&, so the deleted non-const version is selected
}
```

`g` is a non-const lvalue, the `fd` in the call pattern is `F&`, and overload resolution selects the deleted non-const `operator()`, so `g()` must be ill-formed. If it is changed to `const auto g = ...`, `g()` is well-formed and calls the const version.

If an implementation simply wrote four constrained `operator()`s (`&`, `const&`, `&&`, `const&&`), the non-const one would drop out because its constraint is not satisfied, and `g()` would silently select the wrapper's `const&` version and call the target's const overload instead, no longer expression-equivalent to the call pattern. So an implementation must explicitly delete the corresponding overload when the call pattern is ill-formed, rather than letting it disappear. libc++'s `__functional/perfect_forward.h` does exactly this: each qualified version is paired with a `= delete` version.

### Simple call wrappers (¶6)

¶6 A **simple call wrapper** ([[g:simple-call-wrapper]]) is a perfect forwarding call wrapper that meets *Cpp17CopyConstructible* and *Cpp17CopyAssignable*, and whose copy constructor, move constructor and assignment operators are all non-throwing `constexpr` functions. In the standard library only `mem_fn` returns this layer ([[func.memfn]]): its only state is a member pointer, which can naturally be copied and assigned unconditionally.

`bind_front` cannot achieve this, because its state entities are arbitrary user-provided types: they may be move-only (`unique_ptr`), their copying may throw (`std::string`), or they may not be assignable (a lambda with reference members).

### Copying, moving and type identity (¶7, ¶8)

¶7 The copy and move constructors of an argument forwarding call wrapper appear to copy or move its state entities one by one. Note 2 points out that their exception specifications and `constexpr`-ness therefore match those of the implicitly defined versions. The result of `bind_front` with a bound `unique_ptr` can only be moved; when all state entities can be moved without throwing, the wrapper's move constructor is `noexcept`, which determines whether it is moved or copied when a `vector` holding it grows. ¶7 only constrains the constructors; assignment operators are specified by each component individually.

¶8 Argument forwarding call wrappers returned by the same standard library function template have the same type as long as the types of their state entities are the same. `add` and `mul` are both `int(int, int)`, which both decay to `int(*)(int, int)`, so `std::bind_front(add, 1)` and `std::bind_front(mul, 2)` are the same type and can be used in the two branches of a conditional operator. Two different lambdas have different closure types, and the wrappers that bind them have different types too.

```cpp run title="wrapper_types.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }
static_assert(std::is_same_v<decltype(std::bind_front(add, 1)),
                             decltype(std::bind_front(mul, 2))>);   // ¶8
using Owning = decltype(std::bind_front(add, std::make_unique<int>()));
static_assert(!std::is_copy_constructible_v<Owning>);   // ¶7: the state entity is move-only
static_assert(std::is_move_constructible_v<Owning>);
int main() {
  bool c = true;
  auto g = c ? std::bind_front(add, 1) : std::bind_front(mul, 2);   // same type
  return g(1) - 2;
}
```

!!! impl "How libc++ implements *INVOKE*"
    libc++'s internal `std::__invoke`, `__invoke_result_t` and so on are defined in `__type_traits/invoke.h`. On Clang they forward directly to the compiler builtin `__builtin_invoke`, letting the compiler implement the seven bullets itself and saving a large number of template instantiations. Without this builtin, the fallback implementation uses six alias templates corresponding one-to-one to ¶1.1–¶1.6, plus a catch-all overload for ¶1.7, almost a direct transcription of the wording.

## History and evolution

!!! history
    - C++11: *INVOKE* came into the standard from TR1, serving `bind`, `function`, `thread` and `result_of`. At the time the object side was split into only two cases: the object itself, and everything else (dereferenced).
    - C++17: `std::invoke` became a public function, and `invoke_result` replaced `result_of`. *INVOKE* gained the two `reference_wrapper` bullets ¶1.2 and ¶1.5 ([[LWG2219]]). Before that, `reference_wrapper` went through the dereferencing bullet, but it has no `operator*`, so per the wording `invoke(&S::f, std::ref(s))` was ill-formed.
    - C++20: `invoke`, `reference_wrapper`, `bind`, `not_fn`, `mem_fn` and others became `constexpr` ([[P1065R2]]); `bind_front` was added, and the formulation of perfect forwarding call wrappers and call patterns took its current shape.
    - C++23: `invoke_r` was added ([[P2136R3]]); *INVOKE*&lt;R&gt; forbids binding references to temporaries ([[P2255R2]]).

## Common misconceptions

!!! pitfall "`invoke_r<void>` just changes the return type"
    `std::invoke_r<void>(f)` is equivalent to `static_cast<void>(std::invoke(f))`. In generic code where `R` is specified by the user, `R = void` silently discards a return value that may carry an error code, and `[[nodiscard]]` will not warn either.

## Questions

!!! question "Question 1"
    Does `std::optional<Widget> o = ...; std::invoke(&Widget::draw, o);` compile? Which bullet does it take? What happens when `o` is empty?

<details markdown="1">
<summary>Answer</summary>

It compiles. `optional<Widget>` is neither `Widget` nor derived from it, nor a `reference_wrapper`, so it falls to ¶1.3 and expands to `((*o).*f)()`. `optional` happens to have an `operator*`, so the expression is well-formed.

When `o` is empty, `*o` violates the precondition of `optional::operator*`. In C++26 this is a hardened precondition: a hardened implementation terminates the program as a contract violation, and in other implementations it is undefined behavior. *INVOKE* only requires `*t1` to be syntactically valid and does not care about its semantics.
</details>

!!! question "Question 2"
    According to the current draft, what is the value of `is_invocable_r_v<const std::string&, std::string(*)()>`? What about `is_invocable_r_v<std::string_view, std::string(*)()>`?

<details markdown="1">
<summary>Answer</summary>

The first is false. The result of the call is a `std::string` prvalue, binding it to `const std::string&` requires materializing a temporary, so `reference_converts_from_temporary_v` is true, *INVOKE*&lt;R&gt; is ill-formed per ¶2, and `is_invocable_r` is accordingly false. libc++ in our tests does not implement this yet and still gives true.

The second is true. `string_view` is not a reference type, so the rule does not apply to it, even though the result likewise points into a temporary that is about to be destroyed.
</details>
