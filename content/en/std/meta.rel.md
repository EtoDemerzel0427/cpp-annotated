---
title: Relationships between types
summary: "Predicates for the relationship between two types: whether they are the same type, whether one is a base of the other, whether one implicitly converts to the other, whether something is invocable, and whether two types are layout-compatible."
updated: 2026-10-19
---

!!! tldr
    - `is_same` requires the types to be exactly the same, cv-qualification included; type aliases do not create new types.
    - `is_base_of` only asks about inheritance, and private or ambiguous bases count; to know whether a `D*` can be used as a `B*`, ask `is_convertible<D*, B*>` or `std::derived_from`.
    - `is_convertible<From, To>` is defined as whether a hypothetical statement `return declval<From>();` is well-formed, so it judges by copy-initialization, ignores `explicit`, and `From` is an xvalue.
    - The `is_invocable` family judges invocability by *INVOKE*, so member pointers count as callable; `is_invocable_r` also rejects calls that would return a dangling reference.
    - Most of these predicates require their arguments to be complete types; violating this precondition is undefined behavior, and compilers usually do not diagnose it.

The templates in [meta.rel] answer what relationship holds between two types. Each is a **binary type trait** ([[g:cpp17-binary-type-trait|Cpp17BinaryTypeTrait]], [[meta.rqmts]]): it derives from `true_type` when the condition holds and from `false_type` otherwise (paragraphs 1–2). In everyday use you write the corresponding variable template, such as `is_same_v<T, U>`.

## The same type: `is_same`

`is_same<T, U>` is true if and only if `T` and `U` name the same type with the same cv-qualifications.

```cpp run title="is-same.cpp" ok
#include <cstddef>
#include <type_traits>

static_assert( std::is_same_v<int, signed>);         // two spellings of the same type
static_assert(!std::is_same_v<int, const int>);      // different cv
static_assert(!std::is_same_v<char, signed char>);   // the three char types are all distinct
static_assert(!std::is_same_v<long, long long>);     // same width, still different types
static_assert( std::is_same_v<std::remove_cv_t<const int>, int>);

int main() {}
```

Type aliases (`typedef`, `using`) only give an existing type another name, so `is_same_v<std::size_t, unsigned long>` is true on LP64 platforms. `char`, `signed char` and `unsigned char` are three distinct types ([[basic.fundamental]]), and `long` and `long long` are two types even when both are 64 bits. To ignore cv, strip it first with `remove_cv_t`.

## Base class relationship: `is_base_of`

```cpp run title="is-base-of.cpp" ok
#include <type_traits>

struct B {};
struct B1 : B {};
struct B2 : B {};
struct D : private B1, private B2 {};

static_assert( std::is_base_of_v<B, D>);        // private and ambiguous, still a base
static_assert( std::is_base_of_v<const B, D>);  // cv ignored
static_assert( std::is_base_of_v<B, const B>);  // the same class counts too
static_assert(!std::is_base_of_v<D, B>);
static_assert(!std::is_base_of_v<B&, D&>);      // references are not classes
static_assert(!std::is_base_of_v<int, int>);    // not a class, so same type does not count

static_assert(!std::is_convertible_v<D*, B*>);  // yet the pointer does not convert

int main() {}
```

This code is adapted from the standard's Example 1 (paragraph 5). `D` has two `B` subobjects, both obtained through private inheritance. `B` is still a base class of `D` (Note 1), so `is_base_of_v<B, D>` is true; but the conversion from `D*` to `B*` is both ambiguous and inaccessible ([[conv.ptr]]), so `is_convertible_v<D*, B*>` is false.

The condition of `is_base_of<Base, Derived>` is: ignoring cv, `Base` is a base class of `Derived` ([[class.derived]]), or both are the same non-union class. Unions cannot take part in inheritance, so `is_base_of_v<U, U>` is false for a union `U`.

If generic code goes on to do a pointer conversion, the constraint should be `is_convertible_v<D*, B*>`, or the C++20 concept `std::derived_from<D, B>`, which checks both the base relationship and convertibility.

### `is_virtual_base_of` {{c++26}}

`is_virtual_base_of<Base, Derived>` tells whether `Base` is a virtual base class of `Derived` ([[class.mi]]), directly or indirectly, ignoring cv. Private, protected or ambiguous virtual bases count as well (Note 2), and a class is never its own virtual base (Note 3).

```cpp run title="is-virtual-base-of.cpp" ok
#include <type_traits>

struct V {};
struct M1 : virtual V {};
struct M2 : virtual V {};
struct MM : M1, M2 {};
struct B {};
struct N : B {};

static_assert( std::is_virtual_base_of_v<V, M1>);
static_assert( std::is_virtual_base_of_v<V, MM>);  // indirect virtual base
static_assert(!std::is_virtual_base_of_v<B, N>);   // ordinary base
static_assert(!std::is_virtual_base_of_v<V, V>);   // Note 3

int main() {}
```

The location of a virtual base subobject is only known at run time, so you cannot `static_cast` down from a virtual base to a derived class ([[expr.static.cast]]), and member pointers cannot be converted across a virtual base. Generic code doing such conversions can use this trait to rule out virtual bases first.

## Implicit conversion: `is_convertible`

¶6 defines `is_convertible<From, To>` with a piece of code:

!!! std
    The predicate condition for a template specialization `is_convertible<From, To>` shall be satisfied if and only if the return statement in the following code would be well-formed, including any implicit conversions to the return type of the function: `To test() { return declval<From>(); }`

That is, `is_convertible` asks whether an expression of type `From` can become a `To` through a `return` statement. A `return` statement performs copy-initialization, which gives three properties.

First, `explicit` constructors and `explicit` conversion functions do not participate. `is_convertible_v<int, Ex>` is false for `struct Ex { explicit Ex(int); };`, while `is_constructible_v<Ex, int>` (direct-initialization) is true. `std::pair`, `std::optional` and others exploit exactly this difference by writing `explicit(!is_convertible_v<U, T>)`: the wrapper converts implicitly only if the element does.

Second, `declval<From>()` has type `From&&`, and the expression is an [[g:xvalue|xvalue]], not a prvalue. The copy elision guaranteed in C++17 ([[class.copy.elision]]) applies only to prvalues, so initializing the return object from an xvalue needs a move constructor:

```cpp run title="convertible-self.cpp" ok
#include <type_traits>

struct NM {
  NM() = default;
  NM(NM&&) = delete;
};

NM make() { return NM(); }  // OK: a prvalue, no move needed
static_assert(!std::is_convertible_v<NM, NM>);

int main() {}
```

By this definition, a non-movable type is not convertible to itself. This matches the intent of the definition: `is_convertible` asks whether an expression can be converted, and an xvalue of a non-movable type really cannot initialize a new object.

Third, `return` is used rather than `To t = declval<From>();` so that references, arrays, function types and `void` all get definite results (Note 4):

| `From → To` | Result | Reason |
|---|---|---|
| `void → void` | `true` | A `void` function can `return` a `void` expression ([[stmt.return]]) |
| `int → void`, `void → int` | `false` | The expression does not match the return type |
| `int → int[1]`, `int() → int()` | `false` | Functions cannot return arrays or functions |
| `int() → int(&)()`, `int() → int(*)()` | `true` | `declval<int()>()` is a function lvalue, which can bind a reference or convert to a pointer |
| `int[3] → int*` | `true` | An array xvalue can convert to a pointer |

The second half of ¶6 sets the scope of the check. Access checking is performed in a context unrelated to both `From` and `To`, so private conversion functions do not count as usable. The operand of `return` is an [[g:unevaluated-operand|unevaluated operand]], and only the validity of the [[g:immediate-context|immediate context]] of the initialization is considered. Note 5 reminds that initialization can have side effects such as instantiating class templates or implicitly defining special member functions; these side effects are not in the immediate context, and errors in them make the whole program ill-formed rather than making the trait `false`.

`is_nothrow_convertible` {{c++20}} additionally requires the conversion to be known not to throw (by the rules of the `noexcept` operator, [[expr.unary.noexcept]]).

## Invocation: the `is_invocable` family

`is_invocable<Fn, Args...>` tells whether the expression *INVOKE*`(declval<Fn>(), declval<Args>()...)` is well-formed as an unevaluated operand. *INVOKE* is the exposition-only operation defined in [[func.require#1]], on which `std::invoke` is built. It unifies three kinds of call:

1. an ordinary function call `f(args...)`, where `f` can be a function, a function pointer, or an object with `operator()`;
2. a member function pointer plus an object: the object can be a class object, a `reference_wrapper`, or a pointer (including dereferenceable objects such as smart pointers);
3. a data member pointer plus an object, whose result is a reference to that member.

```cpp run title="is-invocable.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>

struct S { int m; int f(int) const; };
using PMF = int (S::*)(int) const;
using RW = std::reference_wrapper<S>;
using UP = std::unique_ptr<S>;

static_assert( std::is_invocable_v<PMF, const S&, int>);
static_assert( std::is_invocable_v<PMF, S*, long>);  // long → int
static_assert( std::is_invocable_v<PMF, RW, int>);
static_assert( std::is_invocable_v<PMF, UP&, int>);  // *t1 first
static_assert(!std::is_invocable_v<PMF, S*>);        // missing argument
static_assert( std::is_invocable_r_v<long, int S::*, S&>);
static_assert( std::is_invocable_r_v<void, int (*)()>);

int main() {}
```

`is_invocable_r<R, Fn, Args...>` uses *INVOKE*`<R>` instead: if `R` is `void`, the result of the call is discarded; otherwise the result must be implicitly convertible to `R`. Since C++23 ([[P2255R2]]) there is one more rule: if binding the result to a reference type `R` would bind to a temporary object, *INVOKE*`<R>` is ill-formed. By this rule `is_invocable_r_v<const long&, int(*)()>` should be false, because the `int` result would first be converted to a temporary `long` and then bound by the reference, dangling immediately after return.

!!! impl "libc++ does not yet implement the dangling check"
    With Clang 23 and libc++, `std::is_invocable_r_v<const long&, int(*)()>` is `true`, contrary to the current draft.

`is_nothrow_invocable` and `is_nothrow_invocable_r` additionally require the call to be known not to throw. Since C++17 `noexcept` is part of the function type, so only types like `void(*)() noexcept` make `is_nothrow_invocable_v` true; a plain `void(*)()` does not.

### `is_applicable`

`is_applicable<Fn, Tuple>` and `is_nothrow_applicable` are post-C++23 wording corresponding to `std::apply`: whether `Fn` can be called with the elements of a tuple expanded as arguments. The result type is given by `apply_result` in [[meta.trans.other]].

¶3 defines for this purpose the exposition-only *ELEMS-OF*`(T)`: with `n` being `tuple_size_v<remove_reference_t<T>>`, it is the pack `get<0>(declval<T>()), …, get<n-1>(declval<T>())`. The condition also requires `Tuple` to satisfy the exposition-only concept *tuple-like* ([[tuple.like]]), so for a type like `int` that is not a tuple the result is `false`, with no error at instantiation. libc++ (with Clang 23) does not provide these two traits yet.

## Layout compatibility and pointer-interconvertibility {{c++20}}

These two traits come from [[P0466R5]] and let the library query two concepts from the core language:

- `is_layout_compatible<T, U>`: `T` and `U` are [[g:layout-compatible-types|layout-compatible]] ([[basic.types.general]]); cv does not affect the result. For standard-layout classes this means their [[g:common-initial-sequence|common initial sequence]] comprises all non-static data members; for enumerations, that their underlying types are the same ([[dcl.enum]]).
- `is_pointer_interconvertible_base_of<Base, Derived>`: `Derived` is unambiguously derived from `Base`, and every `Derived` object is [[g:pointer-interconvertible|pointer-interconvertible]] with its `Base` subobject ([[basic.compound]]), i.e. they have the same address and can be converted to each other with `reinterpret_cast`; or both are the same non-union class. In practice this requires `Derived` to be a standard-layout class.

The same proposal also added two functions for members in [[meta.member]].

!!! impl "libc++ does not provide these two traits"
    libc++ (with Clang 23) has no `std::is_layout_compatible` or `std::is_pointer_interconvertible_base_of`, and does not define the corresponding feature-test macros. Clang 23 provides the builtins behind them, which can be used to check the semantics directly; GCC's libstdc++ provides the `std::` versions.

    ```cpp run title="layout-builtins.cpp" ok
    struct A { int a; };
    struct B { int b; };
    struct C : A, B {};  // members spread over two classes: not standard-layout
    struct D : A {};     // standard-layout

    struct P { int x; char y; };
    struct Q { const int u; char v; };  // cv does not matter
    struct R { int x; char y; char z; };
    enum class E1 : int {};
    enum class E2 : int {};

    static_assert( __is_layout_compatible(P, Q));
    static_assert(!__is_layout_compatible(P, R));
    static_assert( __is_layout_compatible(E1, E2));
    static_assert(!__is_layout_compatible(E1, int));
    static_assert( __is_pointer_interconvertible_base_of(A, D));
    static_assert(!__is_pointer_interconvertible_base_of(A, C));
    static_assert( __is_pointer_interconvertible_base_of(A, A));

    int main() {}
    ```

## Preconditions

Most of these templates require their arguments to be complete types, `void`, or arrays of unknown bound. `is_base_of` and `is_pointer_interconvertible_base_of` relax this slightly: `Derived` must be complete only if the two are different non-union classes, because a class's bases cannot be known without seeing its definition.

Violating a precondition is undefined behavior, and compilers usually do not diagnose it. In our tests Clang silently gives `false` for `is_convertible<Incomplete, int>`. Even if the arguments meet the preconditions, if the result depends on a type that is not yet completely defined and would differ once that type is complete, the behavior is undefined as well ([[meta.rqmts#5]]). For example, asking whether `Incomplete*` converts to `Base*` may give different answers before and after `Incomplete` is defined.

¶4 says that a `declval<T>()` appearing in the definitions is treated as a trivial function call and is not an [[g:odr-use|odr-use]] of `declval`. `declval` may otherwise only appear in unevaluated operands; this rule frees the definitions above from worrying about that restriction.

## Pitfalls

!!! pitfall "The argument orders all differ"
    `is_convertible<From, To>` puts the source first, `is_base_of<Base, Derived>` puts the base first, and `is_assignable<T, U>` puts the target first. The C++20 concept `std::convertible_to<From, To>` matches `is_convertible`, but `std::derived_from<Derived, Base>` puts the derived class first.

## Questions

!!! question "Question 1"
    Given `struct A {}; struct B : A {};`, what are `is_convertible_v<B, A>`, `is_convertible_v<A, B>`, `is_convertible_v<B&, A&>` and `is_convertible_v<B[2], A*>`?

<details markdown="1">
<summary>Answer</summary>

`true`, `false`, `true`, `true` respectively (verified with Clang 23).

- `B → A`: `return declval<B>();` copy-initializes an `A` from a `B` xvalue, selecting `A`'s move constructor (the parameter `A&&` can bind to a derived object), i.e. object slicing.
- `A → B`: there is no implicit conversion from base to derived.
- `B& → A&`: a reference can bind to the base class subobject of a derived object.
- `B[2] → A*`: an array-to-pointer conversion gives `B*`, then a derived-to-base pointer conversion; the two can form one standard conversion sequence ([[over.ics.scs]]).

The last one shows that being convertible is not the same as being safe to use: doing pointer arithmetic through this `A*` to reach the second element is UB, because pointer arithmetic requires the pointed-to type to be similar to the array element type ([[expr.add]]).
</details>

!!! question "Question 2"
    How do `is_invocable_v<int (S::*)(), S>` and `is_invocable_v<int (S::*)() &, S>` differ?

<details markdown="1">
<summary>Answer</summary>

`declval<S>()` is an xvalue of type `S`. The first member function has no ref-qualifier and can be called on an xvalue, so the result is true. The second has a `&` qualifier and can only be called on an lvalue object ([[over.match.funcs]]), so the result is false. With `is_invocable_v<int (S::*)() &, S&>` it becomes true.
</details>

## Quick reference

| Predicate | Condition |
|---|---|
| `is_same<T, U>` | Same type, same cv too |
| `is_base_of<Base, Derived>` | A base class (including private and ambiguous ones) or the same non-union class, ignoring cv |
| `is_virtual_base_of<Base, Derived>` {{c++26}} | A virtual base, ignoring cv; a class is not its own virtual base |
| `is_convertible<From, To>` | `To test() { return declval<From>(); }` is well-formed |
| `is_nothrow_convertible<From, To>` {{c++20}} | Convertible and does not throw |
| `is_layout_compatible<T, U>` {{c++20}} | Layout-compatible |
| `is_pointer_interconvertible_base_of<Base, Derived>` {{c++20}} | An unambiguous base that is pointer-interconvertible with derived objects, or the same non-union class |
| `is_invocable<Fn, Args...>` | *INVOKE*`(declval<Fn>(), declval<Args>()...)` is well-formed |
| `is_invocable_r<R, Fn, Args...>` | *INVOKE*`<R>(...)` is well-formed and the result does not bind to a temporary |
| `is_nothrow_invocable(_r)` | The above, and does not throw |
| `is_applicable<Fn, Tuple>` | `Tuple` is *tuple-like* and the expanded call is valid |
