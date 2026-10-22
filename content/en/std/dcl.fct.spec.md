---
title: Function specifiers
summary: "There are only two function specifiers, virtual and explicit: which declarations they may appear on, how explicit(bool) makes a function conditionally explicit, and a C++20 incompatibility caused by parentheses after explicit."
updated: 2026-10-19
---

!!! tldr
    - There are only two function specifiers, `virtual` and `explicit`; both may appear only on member function declarations inside a class definition, not on out-of-class definitions.
    - `virtual` is used only on the initial declaration of a non-static member function; an overrider in a derived class is virtual even without `virtual`.
    - `explicit` is used only on constructors and conversion functions, keeping them out of implicit conversions and copy-initialization.
    - C++20's `explicit(condition)` decides whether a function is explicit from a bool constant expression; this expression may not narrow.
    - A `(` directly after `explicit` is always taken as the start of `explicit(condition)`, so the C++17 `explicit (S)(const S&);` is no longer valid in C++20.

C++ has only two **function specifiers** (*function-specifier*) left: `virtual` and the *explicit-specifier* (`explicit` or `explicit(constant-expression)`). This subclause only specifies where they may be written; their semantics are in [[class.virtual]] (virtual functions and overriding) and in [[class.conv.ctor]] and [[class.conv.fct]] (converting constructors and conversion functions). Before C++17, `inline` was also a function specifier; it then became usable on variables as well, and got its own subclause, [[dcl.inline]].

## Functions only, and no repetition (¶1)

```cpp error
virtual int x;                        // error: virtual can only be used on functions
struct S {
    explicit explicit(true) S(int);   // error: two explicit-specifiers
    virtual virtual void f();         // error: virtual repeated (Clang only warns)
};
```

¶1 Function specifiers can appear only in function declarations. In the specifier sequence of a declaration, an *explicit-specifier* and `virtual` may each appear at most once.

## virtual goes on the initial in-class declaration (¶2)

```cpp run ok
struct B {
    virtual void f();       // initial declaration: write virtual here
    virtual ~B() = default;
};
void B::f() { }             // out-of-class definition: can't write virtual again
int main() { B b; b.f(); }
```

¶2 `virtual` can only be used on the **initial declaration** of a non-static member function, that is, the place in the class definition where it is first declared. Each of the following lines violates this rule:

```cpp error
struct B { virtual void f(); };
virtual void B::f() { }                  // error: an out-of-class definition is not the initial declaration
struct C { virtual static void g(); };   // error: a static member function can't be virtual
virtual void free_function();            // error: not a member function
struct D { friend virtual void h(); };   // error: a friend function is not a member of D
```

Whether a function is virtual determines whether the class needs a vtable pointer and which slots the vtable has, which must be settled by the end of the class definition. An out-of-class definition only provides the function body and can't change the class's layout.

A function in a derived class that overrides a virtual function of a base class is virtual even without `virtual` ([[class.virtual#2]]). Writing `override` on overriders is recommended; it is a *virt-specifier*, not a function specifier, and makes the compiler check that the function really overrides some virtual function.

## explicit is for constructors and conversion functions (¶3)

```cpp run ok
struct Handle {
    explicit Handle(int fd) : fd(fd) { }
    explicit operator bool() const { return fd >= 0; }
    int fd;
};
void take(Handle) { }
int main() {
    Handle h(3);           // OK: direct-initialization
    Handle h2{4};          // OK: direct-list-initialization
    // Handle h3 = 5;      // error: copy-initialization
    // take(6);            // error: argument passing is copy-initialization too
    // Handle h4 = {7};    // error: an explicit constructor was chosen
    take(Handle(6));       // OK: explicit conversion
    if (h) { }             // OK: contextual conversion to bool
    // bool b = h;         // error: copy-initialization
    bool b2 = static_cast<bool>(h2);
    return b2 ? 0 : 1;
}
```

¶3 An *explicit-specifier* can only be used in the declaration of a constructor or conversion function within its class definition. An out-of-class definition can't repeat `explicit`, and an ordinary member function can't have it:

```cpp error
struct S {
    explicit S(int);
    explicit void f();     // error: not a constructor or conversion function
};
explicit S::S(int) { }     // error: not within the class definition
```

Deduction guides can also have an *explicit-specifier*; that is the deduction guide's own syntax, see [[temp.deduct.guide]].

The effects of `explicit` are spread over the subclauses on initialization and overload resolution. In summary:

- **Copy-initialization** (`T x = a;`, passing by value, returning by value) doesn't consider explicit constructors ([[over.match.copy]]).
- **Copy-list-initialization** (`T x = {a, b};`, `return {a, b};`) does include explicit constructors in overload resolution; if one of them is finally chosen, the program is ill-formed ([[over.match.list]]).
- Direct-initialization, direct-list-initialization and explicit conversions can use explicit constructors.
- Explicit conversion functions are used only for direct-initialization, explicit conversions, and contextual conversion to bool (`if (x)`, `!x`, `x && y`). The `explicit operator bool()` idiom relies on this ([[class.conv.fct]]).

Because of the second point, `explicit` is meaningful on constructors with several parameters too: it forbids forms like `T x = {a, b};` and `return {a, b};`.

## explicit(condition) {{c++20}}

### Conditional explicitness with one constructor

```cpp run ok
#include <type_traits>
#include <string>
template<class T>
struct Wrapper {
    T value;
    template<class U>
        requires std::is_constructible_v<T, U>
    explicit(!std::is_convertible_v<U, T>)   // explicit only when U isn't implicitly convertible to T
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

struct Path { explicit Path(const char*) { } };

int main() {
    Wrapper<std::string> a = "hello";   // OK: const char* converts implicitly to string
    Wrapper<Path> b("dir");             // OK: direct-initialization
    // Wrapper<Path> c = "dir";         // error: this specialization's constructor is explicit
    (void)a; (void)b;
}
```

`Wrapper<T>` wants this: when `U` is implicitly convertible to `T`, `Wrapper<T>` is implicitly constructible from `U` too; otherwise it can only be constructed explicitly. In C++17 this needed two nearly identical constructors, one with `explicit` and one without, made mutually exclusive with SFINAE. `explicit(condition)` makes one constructor enough ([[P0892R2]]). The constructors of `std::pair`, `std::tuple`, `std::optional`, `std::expected` and others in the standard library are written `explicit(see below)`, meaning exactly this kind of condition.

### The condition must be a non-narrowing bool constant (¶4)

¶4 The expression in parentheses must be a **contextually converted constant expression of type bool** ([[expr.const.const]]). If its value is `true`, the function is explicit; otherwise it isn't. `explicit` without parentheses is equivalent to `explicit(true)`.

Such a constant expression doesn't allow narrowing conversions, so `explicit(2)` is not allowed:

```cpp error
struct S {
    explicit(sizeof(char[2])) S(char);  // error: 2 → bool is a narrowing conversion
    explicit(sizeof(char)) S(bool);     // OK: 1 → true doesn't narrow
    explicit(2 > 1) S(int);             // OK: already a bool
};
```

The conditions of `static_assert` and `if constexpr` are different: since C++23 they allow narrowing to bool ([[dcl.pre#13]]), so `static_assert(sizeof(char[2]))` is valid.

### The parenthesis always belongs to explicit

¶4 Its last sentence says that a `(` immediately following `explicit` is always parsed as part of the *explicit-specifier*. This removes an ambiguity, at the cost of a C++17-to-C++20 incompatibility ([[diff.cpp17.class#1]]):

```cpp error
struct S {
    explicit (S)(const S&);   // C++17: an explicit copy constructor with a parenthesized declarator
                              // C++20: read as explicit(S); S is not an expression, error
};
```

C++17 allowed parentheses around a constructor's declarator, so this line used to be an explicit copy constructor. To keep the parentheses now, write `explicit(true) (S)(const S&);`.

!!! impl "Implementation notes"
    - The expression in `explicit(condition)` can depend on template parameters and is evaluated at instantiation. Clang 23's diagnostic for narrowing is "explicit specifier argument evaluates to 2, which cannot be narrowed to type 'bool'".
    - `explicit` is not part of the function type and doesn't enter the mangled name; it is just a filter during overload resolution, so you can't overload on the presence or absence of `explicit`.

!!! history "History"
    - C++98: there were three function specifiers, `virtual`, `explicit` and `inline`; `explicit` only had an effect on constructors.
    - C++11: `explicit` can be used on conversion functions; with list-initialization, `explicit` also became meaningful for constructors with several parameters. `override` and `final` were added as *virt-specifier*s.
    - C++17: `inline` can be used on variables and is no longer a function specifier; deduction guides can have `explicit`.
    - C++20: `explicit(condition)` ([[P0892R2]]); virtual functions can be `constexpr`.

!!! pitfall "Common misconceptions"
    - An overrider must be written with `virtual` to be virtual: it needn't be; an overrider is automatically virtual, and writing `override` is better.
    - explicit only matters for single-parameter constructors: since C++11 it also affects copy-list-initialization.
    - An explicit conversion function can never be used implicitly: contextual conversion to bool is the exception.

!!! summary "Summary"
    | Specifier | Applies to | Where | Effect |
    |---|---|---|---|
    | `virtual` | Non-static member functions | Only on the initial in-class declaration | Dynamic dispatch ([[class.virtual]]) |
    | `explicit`, `explicit(true)` | Constructors, conversion functions | Only within the class definition | Not used for copy-initialization and implicit conversions |
    | `explicit(false)` | Same | Same | Same as not writing it |
    | `explicit(condition)` | Same | Same | The condition must be a non-narrowing bool constant expression |

!!! question "Question"
    Are the `return` statement and the initialization of the variable `a` below well-formed?

    ```cpp
    struct A { explicit A(int, int); A(long, long); };
    A f() { return {1, 2}; }
    A a{1, 2};
    ```

<details markdown="1">
<summary>Answer</summary>

`return {1, 2};` is copy-list-initialization. Overload resolution considers both `A(int, int)` and `A(long, long)`; the former is a better match and is chosen; it is explicit, so `f` is ill-formed ([[over.match.list]]). The compiler won't fall back to `A(long, long)`; Clang 23 reports "chosen constructor is explicit in copy-initialization".

`A a{1, 2};` is direct-list-initialization, which can use explicit constructors, so it is well-formed.
</details>
