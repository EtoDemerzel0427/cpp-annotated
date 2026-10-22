---
title: Type properties
summary: "The type property predicates of Table 54: is_constructible is defined by a hypothetical variable definition, and the trivial and nothrow variants look at what that definition actually calls; plus class properties, is_assignable, is_destructible, has_unique_object_representations, and C++23's reference_constructs_from_temporary."
updated: 2026-10-19
---

!!! tldr
    - `is_constructible_v<T, Args...>` is true if and only if the direct-initializing variable definition `T t(declval<Args>()...);` is well-formed; so `explicit` constructors count, private constructors do not.
    - Only the immediate context of the initialization is checked: an unconstrained constructor template makes the trait answer true even when actual construction would fail to compile in the function body.
    - `is_trivially_*` and `is_nothrow_*` look at the operations that variable definition actually calls; Clang counts the destruction of `t` too.
    - `is_trivially_copyable` is a core-language class property and is not the same thing as `is_trivially_copy_constructible`.
    - Most predicates in the table require their arguments to be complete types; violating that is undefined behavior.

Table 54 has three columns: template, condition and preconditions. The condition determines `value`; if a precondition is violated, the behavior is undefined ([[structure.specifications#3.4]]; for the rules on incomplete types see [[type.traits]]).

## 1. `is_constructible`: a hypothetical variable definition (¶9)

```cpp title="immediate-context.cpp" run ok
#include <type_traits>

struct Ex { explicit Ex(int); };
struct Priv { private: Priv(int); };
struct Lazy {
    template<class T> Lazy(T t) { t.no_such_member(); }
};

static_assert( std::is_constructible_v<Ex, int>);     // explicit counts
static_assert(!std::is_convertible_v<int, Ex>);       // implicit conversion does not work
static_assert(!std::is_constructible_v<Priv, int>);   // access check fails → false
static_assert( std::is_constructible_v<Lazy, int>);   // only the declaration is looked at → true
// Lazy x(1);   // actual construction instantiates the body → hard error

int main() {}
```

`is_default_constructible`, `is_copy_constructible`, all of `is_trivially_*constructible` and `is_nothrow_*constructible` are built on `is_constructible`.

!!! std
    The predicate condition for a template specialization `is_constructible<T, Args...>` shall be satisfied if and only if the following variable definition would be well-formed for some invented variable `t`: `T t(declval<Args>()...);`

¶9 The condition for `is_constructible<T, Args...>` holds if and only if, for some invented variable `t`, the variable definition `T t(declval<Args>()...);` is well-formed. Table 54 first excludes two cases: when `T` is a function type or *cv* `void`, the result is `false`.

The following all follow from it being a direct-initializing variable definition:

| Rule | Example | Result |
|---|---|---|
| Direct-initialization, so `explicit` constructors are usable | `is_constructible_v<Ex, int>` | `true` |
| Since C++20 parentheses can initialize aggregates | `is_constructible_v<Agg, int, int>`, `is_constructible_v<int[2], int, int>` | `true` |
| A non-const lvalue reference cannot bind to a temporary from a conversion ([[dcl.init.ref]]) | `is_constructible_v<int&, long&>` | `false` |
| A const lvalue reference can | `is_constructible_v<const int&, long>` | `true` |
| An rvalue reference cannot bind to an lvalue | `is_constructible_v<int&&, int&>` | `false` |
| No arguments means value-initialization | `is_constructible_v<int>`, `is_default_constructible_v<int[3]>` | `true` |
| A variable of array of unknown bound cannot be defined without an initializer | `is_default_constructible_v<int[]>` | `false` |

Note 7 specifies that these notations are never interpreted as function declarations. So `T t();` with no arguments is value-initialization here, not the function declaration it would be parsed as in real code.

¶9 also specifies two things that recur in the definitions of `is_assignable`, `is_convertible`, `invoke_result` and others:

1. Access checking is performed as if in a context unrelated to `T` and any of the `Args`. So a private constructor makes the result `false`, even when the question is asked inside a member function or friend of `T`. A trait's answer must not depend on where it is asked, or the same specialization would have different values in different places.
2. Only the **immediate context** of the variable initialization is considered (the same notion as in [[temp.deduct.general]]). Initialization can have side effects such as instantiating class templates and function templates or generating implicitly-defined functions. Note 8 says these side effects are not in the immediate context, and errors in them make the program ill-formed rather than making the trait return `false`.

`Lazy` at the top is this case: the constructor template is unconstrained and accepts any `T` at the declaration level, so the trait answers true; actual construction fails when the body is instantiated. With C++20 concepts the requirements go into constraints, constraints are checked in the immediate context, and the trait can give an accurate answer.

### Three convenience traits

| Predicate | Definition |
|---|---|
| `is_default_constructible<T>` | `is_constructible_v<T>` |
| `is_copy_constructible<T>` | Same as `is_constructible_v<T, const T&>` if `T` is referenceable, otherwise `false` |
| `is_move_constructible<T>` | Same as `is_constructible_v<T, T&&>` if `T` is referenceable, otherwise `false` |

A **referenceable type** ([[g:referenceable-type]]) is one a reference can be formed to; this excludes `void` and function types with cv- or ref-qualifiers. For `T = int&`, `const T&` collapses to `int&`, so `is_copy_constructible_v<int&>` is true.

!!! pitfall "Move constructible does not mean having a move constructor"
    `is_move_constructible_v<T>` asks whether `T t(declval<T&&>())` is well-formed. For a class with only a copy constructor `T(const T&)` and no declared move constructor, an rvalue binds to `const T&` just fine, so the result is true. Conversely, when the move constructor is explicitly deleted, overload resolution selects the deleted function and the result is false.

## 2. Trivially: `is_trivially_*`

!!! std
    `is_constructible_v<T, Args...>` is `true` and the variable definition for `is_constructible`, as defined below, is known to call no operation that is not trivial.

`is_trivially_constructible` requires `is_constructible_v` to be true and that variable definition to be known to call no non-trivial operation. What matters is what that variable definition actually calls, not whether some special member function of the class is trivial:

```cpp title="trivially.cpp" run ok
#include <type_traits>

struct DMI { int x = 0; };                 // default member initializer
static_assert( std::is_trivially_copyable_v<DMI>);
static_assert(!std::is_trivially_default_constructible_v<DMI>);

struct Tmpl {
    Tmpl() = default;
    Tmpl(const Tmpl&) = default;           // trivial copy constructor
    template<class T> Tmpl(T&);            // a better match for non-const lvalues
};
static_assert( std::is_trivially_copy_constructible_v<Tmpl>);
static_assert(!std::is_trivially_constructible_v<Tmpl, Tmpl&>);

struct NonTrivDtor { ~NonTrivDtor(); };
static_assert(!std::is_trivially_default_constructible_v<NonTrivDtor>);

struct MoveOnly {
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
};
static_assert( std::is_trivially_copyable_v<MoveOnly>);
static_assert(!std::is_trivially_copy_constructible_v<MoveOnly>);

static_assert( std::is_trivially_constructible_v<int, long>);

int main() {}
```

One by one:

1. A default member initializer makes the default constructor non-trivial, so `DMI` is trivially copyable but not trivially default constructible.
2. What counts is whichever function overload resolution selects. `Tmpl`'s copy constructor is trivial, but when the argument is `Tmpl&` the constructor template is selected, which is not trivial.
3. The variable definition `T t(...)` implies that `t` must eventually be destroyed. Clang counts the destruction too, so for a class with a non-trivial destructor `is_trivially_default_constructible` is false, even if its default constructor itself is trivial.
4. For scalar types, built-in conversions are trivial, so `is_trivially_constructible_v<int, long>` is true.

`MoveOnly` shows that `is_trivially_copyable` is not the same as being trivially copy constructible. The former is a core-language class property ([[class.prop]]): at least one eligible copy or move operation, all eligible ones trivial, and a trivial, non-deleted destructor. The latter asks about one specific expression. Generic libraries use `is_trivially_copyable` to decide whether an object representation may be copied with `memcpy`; to decide whether copy construction can be implemented with `memcpy`, the type also needs to be copy constructible.

`is_trivially_assignable<T, U>` works the same way, requiring the assignment expression to be known to call no non-trivial operation. `is_trivially_destructible<T>` requires `is_destructible_v<T>` to be true and `remove_all_extents_t<T>` to be either a non-class type or a class type with a trivial destructor, so `is_trivially_destructible_v<int&>` is true.

## 3. Without throwing: `is_nothrow_*`

`is_nothrow_constructible<T, Args...>` requires `is_constructible_v` to be true and that variable definition to be known not to throw any exceptions ([[expr.unary.noexcept]]). The other `is_nothrow_*` work the same way.

`std::vector` uses this when growing to choose between moving and copying (`std::move_if_noexcept`): it moves elements only if their move constructor does not throw, or if they are not copyable, to preserve the strong exception guarantee.

!!! lawyer "Does the destructor count?"
    As with triviality, the standard's wording does not say explicitly whether that variable definition includes the destruction of `t`; this is a long-standing open library issue. Clang's `__is_nothrow_constructible` chooses to count the destructor:

    ```cpp title="nothrow-dtor.cpp" run ok
    #include <type_traits>

    struct ND { ~ND() noexcept(false); };

    static_assert( std::is_default_constructible_v<ND>);
    static_assert(!std::is_nothrow_default_constructible_v<ND>);   // Clang 23: the destructor may throw → false

    int main() {}
    ```

    Destructors are `noexcept` by default ([[except.spec]]), so only types that explicitly write `noexcept(false)` run into this difference.

`is_nothrow_destructible<T>` requires `is_destructible_v<T>` to be true and the destructor to be known not to throw. `is_nothrow_swappable_with` requires both `swap` expressions not to throw.

## 4. Assignment, swap and destruction

**`is_assignable<T, U>`**: the expression `declval<T>() = declval<U>()` is well-formed as an unevaluated operand. The rules on access checking and immediate context are the same as for `is_constructible` (Note 3). Note that the left side is `declval<T>()`:

```cpp title="is-assignable.cpp" run ok
#include <type_traits>

struct S { int a; };
struct RQ { RQ& operator=(const RQ&) & = default; };   // can only assign to lvalues

static_assert(!std::is_assignable_v<int, int>);    // int&& cannot be assigned to
static_assert( std::is_assignable_v<int&, int>);
static_assert( std::is_assignable_v<S, S>);        // class rvalues can be assigned to
static_assert(!std::is_assignable_v<RQ, const RQ&>);
static_assert( std::is_copy_assignable_v<RQ>);

int main() {}
```

`declval<int>()` is an xvalue of type `int&&`, and built-in assignment requires a modifiable lvalue as the left operand, so `is_assignable_v<int, int>` is false. That is why `is_copy_assignable<T>` is defined as `is_assignable_v<T&, const T&>` and `is_move_assignable<T>` as `is_assignable_v<T&, T&&>` (`T` must be referenceable). A class rvalue can call a member `operator=`, unless the assignment operator has a `&` qualifier.

**`is_swappable_with<T, U>`**: both `swap(declval<T>(), declval<U>())` and `swap(declval<U>(), declval<T>())` are well-formed, with overload resolution performed in the context of swappable values ([[swappable.requirements]]), i.e. considering both `std::swap` and `swap` found by ADL. `is_swappable<T>` equals `is_swappable_with_v<T&, T&>`. `std::swap` requires its arguments to be move constructible and move assignable, so `is_swappable_v` is false for a type whose move constructor is deleted.

**`is_destructible<T>`**: either `T` is a reference type, or `T` is a complete object type and `declval<U&>().~U()` is well-formed, where `U` is `remove_all_extents_t<T>`:

| `T` | `is_destructible_v<T>` | Reason |
|---|---|---|
| `int&` | `true` | Reference types are simply true |
| `int[3]` | `true` | Looks at the element |
| `int[]` | `false` | Not a complete object type |
| `void`, `void()` | `false` | Not object types |
| A class with a deleted or private destructor | `false` | The pseudo-destructor expression is ill-formed |

## 5. Class properties and cv

| Predicate | Condition | Precondition |
|---|---|---|
| `is_const`, `is_volatile` | Top-level const or volatile qualification ([[basic.type.qualifier]]) | |
| `is_empty` | Non-union class; no non-static data members other than subobjects of zero size; no virtual functions or virtual bases; all bases empty | A non-union class must be complete |
| `is_polymorphic` | Polymorphic class ([[class.virtual]]) | Same |
| `is_abstract` | Abstract class ([[class.abstract]]) | Same |
| `is_final` | A class marked `final`, including unions | A class must be complete |
| `has_virtual_destructor` | Has a virtual destructor ([[class.dtor]]) | A non-union class must be complete |
| `is_aggregate` | Aggregate type ([[dcl.init.aggr]]) | Array, complete type or *cv* `void` |
| `is_structural` | Structural type ([[g:structural-type]]) | `remove_all_extents_t<T>` complete or *cv* `void` |
| `is_signed` | For arithmetic types, same as `T(-1) < T(0)`; otherwise `false` | |
| `is_unsigned` | For arithmetic types, same as `T(0) < T(-1)`; otherwise `false` | |
| `is_bounded_array`, `is_unbounded_array` | Array of known, unknown bound | |
| `is_scoped_enum` | Scoped enumeration ([[dcl.enum]]) | |

### `is_const` only looks at the top level

The standard example in ¶6:

```cpp
is_const_v<const volatile int>   // true
is_const_v<const int*>           // false: the pointer itself is not const
is_const_v<const int&>           // false: references cannot be cv-qualified
is_const_v<int[3]>               // false
is_const_v<const int[3]>         // true: an array's cv is its elements' cv
```

An array's cv-qualification is its elements' cv-qualification ([[basic.type.qualifier]]). `is_const_v<void() const>` is also false: the `const` on a function type is a member function qualifier, not a cv-qualification of the type. The example in ¶7 reaches the same conclusions for `remove_const_t`.

### `is_empty` is unrelated to size

`is_empty` is defined structurally; it characterizes taking up no space as a base class or a `[[no_unique_address]]` member, and has no direct relation to the value of `sizeof`:

```cpp title="is-empty.cpp" run ok
#include <type_traits>

struct Empty {};
struct WithNUA { [[no_unique_address]] Empty e; };   // the only member is a zero-size subobject
struct D : Empty {};
struct Poly { virtual ~Poly(); };

static_assert( std::is_empty_v<WithNUA>);   // sizeof(WithNUA) == 1
static_assert( std::is_empty_v<D>);
static_assert(!std::is_empty_v<Poly>);      // has virtual functions
static_assert(!std::is_empty_v<int>);       // not a class

int main() {}
```

### `is_final`, `is_aggregate`, `is_structural`

The example in ¶8 shows that `union U2 final {};` is valid and `is_final_v<U2>` is true. The main use of `is_final` is implementing the empty base optimization: a `final` class cannot be a base, so storage has to fall back to a member (or `[[no_unique_address]]`).

Arrays are always aggregates, so the precondition of `is_aggregate` deliberately allows array types, and `is_aggregate_v<int[]>` is true.

Structural types are the types usable as the type of a constant template parameter ([[temp.param]]). In C++26 reflection, `reflect_constant` requires its argument type to be structural ([[meta.reflection.extract]]). libc++ (with Clang 23) does not provide `std::is_structural` yet.

### `is_signed` is defined by an expression

!!! std
    If `is_arithmetic_v<T>` is `true`, the same result as `T(-1) < T(0)`; otherwise, `false`.

This definition has some less intuitive consequences:

- `is_unsigned_v<bool>` is true: `bool(-1)` is `true`, and `false < true`.
- `is_signed_v<float>` is true.
- `is_signed_v<char>` depends on the implementation: on Apple arm64 `char` is signed, so true; on Linux AArch64 `char` is unsigned, so false.
- Enumerations are not arithmetic types, so `is_signed_v<E>` is false for every enumeration. To ask about an enumeration's signedness, write `is_signed_v<underlying_type_t<E>>`.

```cpp title="is-signed.cpp" run ok
#include <type_traits>

enum E : int { e = -1 };

static_assert( std::is_unsigned_v<bool>);
static_assert( std::is_signed_v<float>);
static_assert(!std::is_signed_v<E> && !std::is_unsigned_v<E>);
static_assert( std::is_signed_v<std::underlying_type_t<E>>);

int main() {}
```

## 6. Core properties

| Predicate | Condition | Precondition |
|---|---|---|
| `is_trivially_copyable` | Trivially copyable type ([[basic.types.general#7]]) | `remove_all_extents_t<T>` complete or *cv* `void` |
| `is_standard_layout` | Standard-layout type | Same |
| `is_implicit_lifetime` {{c++23}} | Implicit-lifetime type | Array, complete type or *cv* `void` |

The meaning of these three traits is entirely determined by the core language; see [[basic.types]] and [[class.prop]]. A few additions from the trait point of view:

- They are all properties of object types. `is_trivially_copyable_v<int&>` and `is_standard_layout_v<int&>` are both false. cv-qualified scalar types are trivially copyable: `is_trivially_copyable_v<const int>` is true, even though it cannot be assigned to.
- Array types are unconditionally implicit-lifetime types, because creating an array object itself requires running no code. So `is_implicit_lifetime_v<std::string[2]>` is true, while `is_implicit_lifetime_v<std::string>` is false.
- `is_trivial` (trivially copyable and trivially default constructible) was deprecated in C++26 and moved to Annex D ([[depr.meta.types]], [[P3247R2]]). Ask `is_trivially_copyable` and `is_trivially_default_constructible` separately instead.

```cpp title="core-properties.cpp" run ok
#include <string>
#include <type_traits>

struct Agg { int a; int b; };

static_assert(!std::is_trivially_copyable_v<int&>);
static_assert( std::is_trivially_copyable_v<const int>);
static_assert( std::is_implicit_lifetime_v<Agg>);
static_assert(!std::is_implicit_lifetime_v<std::string>);
static_assert( std::is_implicit_lifetime_v<std::string[2]>);   // arrays are always implicit-lifetime types
static_assert( std::is_implicit_lifetime_v<int[]>);

int main() {}
```

## 7. `has_unique_object_representations` (¶10)

¶10 The condition holds if and only if `T` is trivially copyable and any two objects of type `T` with the same value have the same object representation ([[g:object-representation]]).

This is the criterion for hashing or comparing byte-wise: equal values imply equal bytes, so `memcmp` or hashing can be done directly on the object representation. It was added in C++17 ([[P0258R2]]), motivated precisely by implementing `std::hash` efficiently.

¶10 also defines "same value": arrays and non-union classes require each direct subobject to have the same value; unions require the same active member with the same value. For scalar types, which ones satisfy the condition is implementation-defined. Note 9 hints that types with padding bits do not, and integral types otherwise do.

| Type | Clang 23 (arm64 macOS) | Reason |
|---|---|---|
| `int`, `int*`, member pointers | `true` | No padding; values and representations correspond one-to-one |
| `bool` | `true` | Only two valid representations, 0 and 1 |
| `float`, `double`, `long double` | `false` | `+0.0 == -0.0`, but the representations differ |
| `struct { char c; int i; }` | `false` | Has padding bytes |
| `struct { int a, b; }` | `true` | No padding |
| A class containing the bit-field `int x : 3` | `false` | The bits outside the bit-field are padding |
| Arrays | Same as the element type | Specified explicitly in Table 54 |

The condition only requires that equal values imply equal representations. NaN not comparing equal to itself is not why floating-point types are excluded; what excludes them is the pair `+0.0` and `-0.0`, which compare equal but have different representations.

## 8. References bound to temporaries {{c++23}}

¶5 first defines the exposition-only expression *VAL*`<T>`:

- ¶5.1 if `T` is a reference or function type, *VAL*`<T>` has the same type and value category as `declval<T>()`;
- ¶5.2 otherwise, *VAL*`<T>` is a prvalue that initially has type `T` (adjusted per [[expr.type]] if `T` is cv-qualified).

| Predicate | Condition |
|---|---|
| `reference_constructs_from_temporary<T, U>` | `T` is a reference type, `T t(VAL<U>);` is well-formed and binds `t` to a temporary object whose lifetime is extended |
| `reference_converts_from_temporary<T, U>` | Same, but the initialization is the copy-initialization `T t = VAL<U>;` |

The difference between them is direct-initialization versus copy-initialization: `explicit` conversion functions are usable only in the former.

```cpp title="ref-from-temp.cpp" run ok
#include <string>
#include <type_traits>

struct X { explicit operator int() const; };
using std::reference_constructs_from_temporary_v;
using std::reference_converts_from_temporary_v;

static_assert( reference_constructs_from_temporary_v<const int&, long>);  // long → int temporary
static_assert( reference_constructs_from_temporary_v<const int&, int>);   // prvalue → materialized
static_assert(!reference_constructs_from_temporary_v<const int&, int&>);  // binds the lvalue directly
static_assert( reference_constructs_from_temporary_v<int&&, int>);
static_assert( reference_constructs_from_temporary_v<const std::string&, const char*>);
static_assert(!reference_constructs_from_temporary_v<int, int>);          // T is not a reference

static_assert( reference_constructs_from_temporary_v<const int&, X>);     // explicit usable
static_assert(!reference_converts_from_temporary_v<const int&, X>);       // explicit not usable

int main() {}
```

`declval<U>()` cannot be used here. For a non-reference `U`, `declval<U>()` returns `U&&`, an xvalue; initializing `const U&` with it binds directly and produces no temporary. But what `reference_constructs_from_temporary<const int&, int>` wants to ask is whether initializing from an `int` prvalue binds to a temporary, and the answer is yes. *VAL* provides a genuine prvalue.

This pair of traits comes from [[P2255R2]] and is used to stop a class of dangling references at compile time:

- In `std::pair<const std::string&, int> p("x", 1);`, `first` would bind to a temporary `std::string` destroyed at the end of the constructor. Since C++23, if `reference_constructs_from_temporary_v<first_type, U1&&>` is true, the corresponding constructor is defined as deleted ([[pairs.pair]]), and likewise for `tuple`.
- [[func.require#2]] specifies that *INVOKE*`<R>` is ill-formed if `reference_converts_from_temporary_v<R, decltype(INVOKE(...))>` is true. By the standard, necessarily dangling code like `std::function<const int&()> f = []{ return 42; };` does not compile, and `is_invocable_r_v<const long&, int(*)()>` is false.

!!! impl "How far libc++ has implemented this"
    With Clang 23 and libc++, `pair` and `tuple` report the situations above with a `static_assert` (reference member 'first' binds to a temporary object…) instead of defining the constructor as deleted. So `is_constructible_v<std::pair<const std::string&, int>, const char*, int>` is still true, contrary to the standard. `std::is_invocable_r_v<const long&, int(*)()>` is also true in libc++; this rule of *INVOKE*`<R>` has not been implemented at the trait level yet.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 The templates in Table 54 provide access to some of the more important properties of types.

¶2 It is unspecified whether the library defines any full or partial specializations of these templates. So you cannot assume that `is_trivially_copyable<X>` is necessarily an instance of the primary template.

¶3 When a template argument is a class template specialization, it may be implicitly instantiated only if the trait's semantics require the argument to be a complete type. So shape-only queries such as `is_class_v<Box<T>>` and `is_const_v<Box<T>>` do not instantiate `Box<T>`, while `is_trivially_copyable_v<Box<T>>` necessarily does.

¶4 For the purpose of defining the templates in this subclause, a call to `declval<T>()` is considered a trivial function call and not an odr-use of `declval`. Otherwise `declval<T&&>()` in `is_trivially_constructible<T, T&&>` would itself be a non-trivial operation and every `is_trivially_*` would be false; the restriction that `declval` is only declared and cannot be used in an evaluated context ([[declval]]) is waived as well.

</details>

## The implementation's view

!!! impl "All Clang builtins"
    In libc++, almost every trait in this subclause forwards directly to a Clang builtin: `__is_constructible`, `__is_trivially_constructible`, `__is_nothrow_constructible`, `__is_assignable`, `__is_trivially_copyable`, `__builtin_is_implicit_lifetime`, `__has_unique_object_representations`, `__reference_constructs_from_temporary` and so on. For example:

    ```cpp
    template <class _Tp>
    struct _LIBCPP_NO_SPECIALIZATIONS is_copy_constructible
        : integral_constant<bool, __is_constructible(_Tp, __add_lvalue_reference_t<const _Tp>)> {};
    ```

    `__add_lvalue_reference_t<const _Tp>` is used rather than `const _Tp&` to handle non-referenceable types: for `void` it gives `const void`, and `__is_constructible(void, const void)` is false, matching the standard's "otherwise `false`".

    Inside the compiler, `__is_constructible` really does construct that hypothetical variable definition during semantic analysis and checks it in an environment that records failure without reporting errors.

## Common mistakes

!!! pitfall "An unconstrained converting constructor makes traits give wrong answers"
    An unconstrained perfect-forwarding constructor like `template<class T> Wrapper(T&&)` makes `is_constructible_v<Wrapper, X>` and `is_convertible_v<X, Wrapper>` true for every `X`, which in turn affects overload resolution in `std::variant`, `std::optional` and others that rely on these traits. Constrain it with `requires` or `enable_if`.

!!! pitfall "`is_trivially_copyable` being true does not mean it can be copied"
    `MoveOnly` is trivially copyable yet cannot be copy-constructed at all. Library code that takes the `memcpy` path based on `is_trivially_copyable` copies the object representation byte-wise. For trivially copyable types this is always valid at the language level ([[basic.types.general#2]]), even if the type's author deleted the copy constructor, which sometimes goes against the author's intent.

!!! ub "Violating preconditions"
    Almost every row of Table 54 has a precondition such as "shall be a complete type, *cv* `void`, or an array of unknown bound". Asking `is_constructible`, `is_trivially_copyable`, `is_nothrow_move_constructible` and the like about an incomplete class is UB. Clang reports an error in most cases, but do not rely on that.

## Questions

!!! question "Question 1"
    For `struct A { A(int) noexcept; ~A(); };`, what are `is_nothrow_constructible_v<A, int>` and `is_trivially_constructible_v<A, int>`?

<details markdown="1">
<summary>Answer</summary>

`~A()` has no explicit exception specification and is implicitly `noexcept` per [[except.spec]], so `is_nothrow_constructible_v<A, int>` is true: the constructor does not throw, and neither does the destructor.

`is_trivially_constructible_v<A, int>` is false: the `A(int)` called is a user-provided constructor, not a trivial operation, and the destructor is also user-provided and non-trivial.
</details>

!!! question "Question 2"
    Why is `is_unsigned_v<bool>` `true`? What about `is_signed_v<char8_t>`?

<details markdown="1">
<summary>Answer</summary>

`bool` is an arithmetic type, and Table 54 computes `bool(0) < bool(-1)`: `bool(-1)` is `true`, and `false < true` holds.

The underlying type of `char8_t` is `unsigned char` ([[basic.fundamental]]), so `char8_t(-1)` is 255 and `char8_t(-1) < char8_t(0)` is false. So `is_signed_v<char8_t>` is false and `is_unsigned_v<char8_t>` is true.
</details>

## Summary

| Family | Defined by | Key points |
|---|---|---|
| `is_constructible` family | Whether `T t(declval<Args>()...);` is well-formed | Direct-initialization; access checked in an unrelated context; immediate context only; false for functions and `void` |
| `is_assignable` family | `declval<T>() = declval<U>()` | The left side usually has to be written as `T&` |
| `is_trivially_*` | The expression above is known to call no non-trivial operation | Looks at the function actually selected; Clang counts the destructor |
| `is_nothrow_*` | The expression above is known not to throw | The basis of `move_if_noexcept`; Clang counts the destructor |
| Core properties | [[basic.types]], [[class.prop]] | Arrays are always implicit-lifetime types |
| `has_unique_object_representations` | Equal values imply equal representations | False for floating-point and for classes with padding |
| `reference_*_from_temporary` | Whether initializing a reference from the prvalue *VAL*`<U>` binds a temporary | Used by `pair`, `tuple` and *INVOKE*`<R>` to prevent dangling |
