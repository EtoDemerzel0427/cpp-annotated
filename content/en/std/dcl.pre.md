---
title: The general syntax of declarations
summary: "Which syntactic forms a declaration can take and which may appear in a function body; how a declaration splits into attributes, specifiers and declarators, and when it introduces a name; typedef, function and object declarations; the shape of structured bindings; static_assert and consteval blocks."
updated: 2026-10-19
---

!!! tldr
    - Function definitions, templates and namespace definitions are not block declarations, so they can't appear in a function body; `using`, `static_assert` and namespace aliases can.
    - Attributes at the start of a declaration appertain to every entity declared; a declaration introduces a name only when the declarator is a plain name.
    - Each declarator in a declaration is classified on its own: with `typedef` it's a typedef declaration, if its type is a function type it's a function declaration, otherwise it's an object declaration, and if the type is something like `void` it's ill-formed.
    - A declaration with no declarator can only declare a class or enumeration, and it must introduce at least one name.
    - The condition of `static_assert` allows a narrowing conversion to `bool`; `static_assert(false)` in a template definition is only checked on instantiation (C++23); the message can be a string computed at compile time (C++26).

## A declaration has three parts (¶4–5)

```cpp run ok
[[maybe_unused]] static int a, b;        // both a and b are maybe_unused
static int c [[maybe_unused]], d;        // only c is
[[noreturn]] void f [[noreturn]] ();     // OK: writing it in both places is allowed
int main() { return d; }
```

¶4 A *simple-declaration* is treated uniformly as three parts:

```text
attribute-specifier-seq(opt)  decl-specifier-seq(opt)  init-declarator-list(opt) ;
```

The three parts are described in [[dcl.attr]], [[dcl.spec]] and [[dcl.decl]] respectively. Leading attributes **appertain to each of the entities declared by the declarators**. Attributes written after the name (the *declarator-id*) appertain only to that one entity ([[dcl.meaning]]). Writing the same attribute in both places is not a conflict, so the declaration of `f` above is valid.

¶5 If the *declarator-id* is a name, that is, an identifier, an operator function name, a conversion function name or a literal operator name, the declaration **introduces** that name. Otherwise it is a qualified name, a destructor name or a *template-id*, and instead of introducing a name it redeclares or defines an existing entity:

```cpp
struct S { void f(); ~S(); };
void S::f() { }                  // qualified name: defines the already declared S::f, introduces no name
S::~S() { }                      // destructor: introduces no name
template<class T> void g(T);
template<> void g<int>(int);     // template-id: introduces no name
```

The rules in [[basic.scope]] for which scope a name binds to all start from this: only declarations that introduce a name bind a name in a scope.

¶5 Its second half says where the type comes from: the type specifiers in the specifier sequence ([[dcl.type]]) and the recursive structure of the declarator together describe a type ([[dcl.meaning]]). Specifiers such as `static` and `inline` take no part.

## Which declarations may appear in a function body (¶1)

```cpp run ok
void f() {
    using I = int;                 // alias declaration
    static_assert(sizeof(I) >= 2); // static_assert
    namespace s = std;             // namespace alias
    int g(int);                    // function declaration (not a definition)
}
int main() { }
```

¶1 lists every syntactic form of a declaration. Among them, the **block declarations** (*block-declaration*) can appear both at namespace scope and in a block:

| Block declaration | Example | See |
|---|---|---|
| *simple-declaration* | `int x = 1, *p;`, `auto [a, b] = pr;` | this page, [[dcl.spec]], [[dcl.decl]] |
| *asm-declaration* | `asm("nop");` | [[dcl.asm]] |
| *namespace-alias-definition* | `namespace fs = std::filesystem;` | [[namespace.alias]] |
| *using-declaration* | `using std::swap;` | [[namespace.udecl]] |
| *using-enum-declaration* | `using enum Color;` | [[enum.udecl]] |
| *using-directive* | `using namespace std;` | [[namespace.udir]] |
| *static_assert-declaration* | `static_assert(N > 0);` | this page |
| *consteval-block-declaration* {{c++26}} | `consteval { ... }` | this page |
| *alias-declaration* | `using I = int;` | [[dcl.typedef]] |
| *opaque-enum-declaration* | `enum class E : int;` | [[dcl.enum]] |

Function definitions, template declarations, deduction guides, namespace definitions, linkage specifications, module imports, explicit instantiations and explicit specializations, and `export` declarations are not in this table, so none of them can appear in a function body. The absence of local function definitions, local templates and local namespaces is a direct consequence of this grammar.

```cpp error
void f() {
    int g() { return 0; }          // error: a function definition is not a block declaration
}
```

## typedef, function or object (¶8–11)

¶8 A *simple-declaration* is classified in this order:

1. If the specifier sequence contains `typedef`: a **typedef declaration**, and each *declarator-id* is a typedef-name ([[dcl.typedef]]);
2. Otherwise, if the type associated with the *declarator-id* is a function type: a **function declaration**;
3. Otherwise, if the type is an object type or a reference type: an **object declaration**;
4. Otherwise (for example, the type is `void`), the program is ill-formed.

The classification is done declarator by declarator:

```cpp error
int f(), x;           // OK: f is a function declaration, x an object declaration
extern void g(),      // OK: function declaration
    y;                // error: void is not an object type
```

References are not objects, but `int& r = x;` is also classified as an object declaration.

¶9 An object definition causes storage of appropriate size and alignment to be reserved and any appropriate initialization to be done ([[dcl.init]]). So `extern int x;` is not a definition and allocates no storage; `int x;` is a definition.

¶10 A function definition is a function declaration followed by a function body. A token sequence starting with `{` or `=` is treated as a function body (`{...}`, `= default;`, `= delete;`) if the type of the *declarator-id* is a function type, and as an initializer otherwise. The decision depends on the declarator's type, not on what follows the `=`.

Note 5 draws two corollaries from this. If a declaration only becomes one of function type after template instantiation, the program is ill-formed ([[temp.spec.general]]). And the function type of a function definition can't come from a typedef-name, because the body accesses the parameters through their names, and parameter names are not part of the type:

<div class="compare" markdown="1">

```cpp error
typedef void F();
F f;      // OK: a function declared with a typedef
F g { }   // error: can't define a function this way
```

```cpp error
template<class T>
struct X { T m; };
X<int()> x;  // error: member m would have
             // function type int()
```

</div>

¶11 A function declaration with no specifiers at all (a *nodeclspec-function-declaration*) can only declare a constructor, destructor or conversion function, which have no return type anyway. A member function can't be redeclared out of class without a definition ([[class.mfct]]), so in practice this form only appears in template-related contexts (note 6):

```cpp run ok
template<class T> struct A { A() { } operator int() { return 0; } };
template<> A<char>::A();          // declaration of an explicit specialization
template A<int>::A();             // explicit instantiation
template<> A<char>::A() { }       // definition of the explicit specialization
int main() { }
```

## Declarations without a declarator (¶6)

```cpp
struct S;              // declares the class name S
struct T { int m; };   // defines and declares the class name T
enum E { e1 };         // declares E and e1
enum { e2 };           // unnamed enumeration, but introduces the enumerator e2
```

¶6 A *simple-declaration* may omit the declarator list only when it **declares a class or enumeration**, that is, when the specifier sequence contains a class definition, an elaborated type specifier with a `class`/`struct`/`union` keyword, or an enumeration definition. The identifiers in these specifiers are then declared as class names, enum names or enumerators. And the declaration must (re)introduce at least one name:

```cpp error
enum { };              // error: introduces no name at all
typedef class { };     // error: unnamed class, and no typedef-name
int;                   // error: not a class or enumeration declaration, and no declarator
static struct T1 { };  // error: static has no object to apply to ([[dcl.stc#1]])
const struct T2 { };   // error: likewise for const ([[dcl.type.cv#1]])
```

A declaration that declares nothing is almost always a typo, such as a forgotten variable name; the `const` in `const struct T2 { };` has nothing to apply to either. Clang 23 gives only on-by-default warnings (the `-Wmissing-declarations` group) for all five lines, which conforms to the standard, since a warning is a diagnostic ([[intro.compliance]]); with `-pedantic-errors` they become errors.

## The shape of structured bindings (¶7)

¶7 A *simple-declaration* or condition with a *structured-binding-declaration* is called a **structured binding declaration** ([[g:structured-binding-declaration|structured binding declaration]]); its semantics are in [[dcl.struct.bind]]. This subclause only restricts its shape:

1. The only allowed specifiers are `constexpr`, `constinit`, `static`, `thread_local`, `auto` and cv-qualifiers. So `inline auto [a, b]`, `extern auto [a, b]`, `int [a, b]` and a constrained `C auto [a, b]` are all disallowed.
2. At most one name may be preceded by `...` (a structured binding pack); if one is, the declaration must declare a templated entity, i.e. it can only appear in a template {{c++26}}.
3. The initializer can only take one of the three forms `= e`, `{ e }`, `( e )`.
4. When used as a condition, `e` must be of non-union class type {{c++26}}; otherwise it is of array or non-union class type.

```cpp run ok
#include <utility>
struct P { int a, b; };
constexpr P cp{1, 2};
constexpr auto [x, y] = cp;                // C++26: constexpr structured binding
static_assert(x == 1);

template<class T> int sum(T t) {
    auto [...xs] = t;                      // C++26: structured binding pack, only in templates
    return (0 + ... + xs);
}

int main() {
    static auto [m, n] = P{3, 4};          // static allowed since C++20
    [[maybe_unused]] auto [u [[maybe_unused]], v] = std::pair{1, 2.0};
    return sum(P{m, n}) - 7;               // returns 0
}
```

```cpp error
#include <utility>
template<class T> concept C = true;
struct P { int a, b; };
C auto [a, b] = std::pair{1, 2};      // error: a constrained placeholder is not allowed
inline auto [c, d] = std::pair{1, 2}; // error: inline is not among the allowed specifiers
auto [...xs] = P{1, 2};               // error: a pack can only appear in a templated entity
```

A constrained `C auto` is disallowed because in a structured binding the type being deduced is that of the whole hidden variable (for example `std::pair<int, int>`), not the types of `a` and `b`. Allowing it would make readers think the constraint applies to each binding.

C++26 also allows structured bindings in conditions; the value of the condition is then the whole object contextually converted to `bool`, not the first binding:

```cpp run ok
struct R { bool ok; int v; explicit operator bool() const { return ok; } };
R parse() { return {true, 42}; }
int main() {
    if (auto [ok, v] = parse())    // the condition is R converted to bool
        return v - 42;
    return 1;
}
```

!!! history "How the structured binding specifiers evolved"
    When structured bindings were introduced in C++17, only `auto` and cv-qualifiers were allowed; `static` and `thread_local` have been allowed since C++20. C++26 added structured bindings in conditions, `constexpr` structured bindings, attributes on each binding, and structured binding packs ([[P1061]]).

## static_assert (¶12–14)

`static_assert` checks a condition at compile time, introduces no name, and can appear at namespace scope, in a class and in a block.

### The condition (¶13)

¶13 The condition `E` is [[g:contextually-converted-to-bool|contextually converted to bool]], and the converted expression must be a constant expression ([[expr.const]]). If its value is `true`, the declaration has no effect; if it is `false`, the `static_assert` **fails** and the program is ill-formed.

Contextual conversion allows narrowing, so converting 8 to `true` in `static_assert(sizeof(int[2]));` is valid. This is a C++23 change ([[P1401R5]]); before that, the required conversion didn't allow narrowing.

```cpp run ok
static_assert(sizeof(int[2]));     // OK: 8 → true, narrowing allowed
static_assert(2);                  // OK
static_assert(sizeof(long) >= 4, "long too small");
int main() { }
```

### static_assert(false) in templates

¶13 also says that when the expression is evaluated in the context of a template definition, the declaration likewise has no effect. This half-sentence was added in C++23 ([[P2593R1]]) and applies to earlier language modes as a defect report. It makes this possible:

```cpp run ok
#include <type_traits>
template<class T> int to_int(T t) {
    if constexpr (std::is_integral_v<T>)
        return static_cast<int>(t);
    else
        static_assert(false, "to_int: T must be integral");   // OK since C++23
}
int main() { return to_int(0L); }
```

Before that, `static_assert(false)` didn't depend on a template parameter, so the compiler could evaluate it and report an error at the template definition even if that branch would never be instantiated, and GCC and Clang did exactly that. People had to write `static_assert(sizeof(T) == 0)` or `static_assert(always_false<T>)`, creating an artificial dependence to defer the check.

Now a `static_assert` in a template definition is never checked there, only after instantiation. A branch discarded by `if constexpr` is not instantiated ([[stmt.if]]), so a `static_assert(false)` in it never fires:

```cpp error
template<class T> void f() { static_assert(false); }   // the definition itself is OK
template void f<int>();     // error: static_assert fails on instantiation
void g() { static_assert(false); }   // error: not in a template, checked immediately
```

### The message (¶12, ¶13.2) {{c++26}}

¶12 The message can be written two ways. If it syntactically matches an [[g:unevaluated-string|unevaluated string]] (a string literal with no encoding prefix, [[lex.string.uneval]]), it is a string. Otherwise it must be an expression `M` such that `M.size()` is implicitly convertible to `std::size_t` and `M.data()` is implicitly convertible to `const char*`.

¶13.2 When the assertion fails, `M.size()` must be a constant expression, whose value we call N; `M.data()` must also be computable during constant evaluation, and the message text is the N characters starting there.

So a `std::string`, a `std::string_view` or a fixed-size buffer of your own can serve as the message, as long as it can be computed at compile time ([[P2741R3]]). In C++23 and earlier, the message could only be a string literal.

```cpp run ok
#include <cstddef>
struct Buf {                                   // a minimal compile-time formatting buffer
    char s[32]{}; std::size_t n = 0;
    constexpr Buf& operator<<(const char* p) { while (*p) s[n++] = *p++; return *this; }
    constexpr Buf& operator<<(std::size_t v) {
        char t[20]; int k = 0;
        do t[k++] = char('0' + v % 10); while (v /= 10);
        while (k) s[n++] = t[--k];
        return *this;
    }
    constexpr std::size_t size() const { return n; }
    constexpr const char* data() const { return s; }
};
template<class T> struct Wrapper {
    static_assert(sizeof(T) <= 8, Buf{} << "sizeof(T) == " << sizeof(T) << ", too big");
};
Wrapper<int> w;        // OK
int main() { }
```

Replace `Wrapper<int>` with a 16-byte type and Clang 23's error message ends with the computed message `sizeof(T) == 16, too big`.

```cpp error
#include <string>
static_assert(false, std::string("built at ") + "compile time");  // error: the message is "built at compile time"
static_assert(false, u8"text");     // error: an unevaluated string can't have an encoding prefix
```

When the assertion succeeds, the message is an unevaluated operand; it only needs to meet the type requirements of ¶12 and need not be a constant expression. ¶14 recommends that implementations include the message text in the diagnostic for a failed assertion; this is only a recommendation, as the standard never specifies the content of diagnostics.

!!! history "How static_assert evolved"
    - C++11: introduced; the message was mandatory and could only be a string literal.
    - C++17: the message can be omitted.
    - C++23: the condition allows narrowing ([[P1401R5]]); `static_assert(false)` in a template definition no longer fails early ([[P2593R1]]).
    - C++26: the message can be a string computed at compile time ([[P2741R3]]); the message string may not have an encoding prefix.

## consteval blocks (¶15) {{c++26}}

¶15 `consteval { compound-statement }` is equivalent to evaluating the following expression, which must be a constant expression:

```text
[] static consteval -> void compound-statement ()
```

That is, an immediate call of a captureless, `static`, `consteval` lambda returning `void`. Its purpose is its side effects: constant evaluation can produce **injected declarations** ([[expr.const.reflect]]), for example generating a definition for an incomplete class with `std::meta::define_aggregate`.

Because it is equivalent to a lambda body, it may contain `return;`, but it can't declare local templates or concepts.

```cpp
struct S;
consteval {
    std::meta::define_aggregate(^^S, {});   // injects the definition struct S { };
}
S s;                                         // OK: S is now complete
```

`consteval` blocks entered the standard together with C++26 static reflection. At the time of writing, Clang 23 doesn't implement static reflection, so this example has not been verified by a compiler.

## Common misconceptions

!!! pitfall "static_assert(false) in a template can go anywhere"
    It is only checked on instantiation. If its location isn't discarded, every instantiation fails; and a template with no valid specialization can still fall under the IFNDR rule in [[temp.res.general]].

!!! pitfall "Leading attributes apply only to the first variable"
    In `[[maybe_unused]] int a, b;` the attribute appertains to both `a` and `b`. To mark only one of them, write the attribute after that name: `int a [[maybe_unused]], b;`.

## Questions

!!! question "Question 1"
    Is each line well-formed or ill-formed?
    ```cpp
    typedef struct { int x; } T, *PT;
    struct { int y; } obj;
    typedef int A, B();
    B b { }
    ```

<details markdown="1">
<summary>Answer</summary>

- Line 1 is well-formed: it defines an unnamed class; `T` is its typedef-name (and also the typedef-name for linkage purposes, [[dcl.typedef#4]]), and `PT` is a pointer type to it.
- Line 2 is well-formed: an unnamed class plus an object declaration, which introduces the name `obj` and so satisfies ¶6.
- Line 3 is well-formed: `A` is an alias for `int`, `B` an alias for the function type `int()`; each declarator is classified separately (¶8).
- Line 4 is ill-formed: `B` is a function type, so the `{` starts a function body (¶10), but the type of a function definition can't come from a typedef-name (note 5).
</details>

!!! question "Question 2"
    Why does `template<class T> void f(T) { if constexpr (false) static_assert(false); }` not produce an error in C++23, while in C++20 the idiom was `static_assert(sizeof(T*) == 0)`?

<details markdown="1">
<summary>Answer</summary>

Since C++23, a `static_assert` in the context of a template definition is not checked; the `if constexpr (false)` branch is discarded and is not instantiated on instantiation either, so it never fires. Under the C++20 rules, `static_assert(false)` is a constant expression that doesn't depend on a template parameter, so the compiler may evaluate it at the definition and report an error. Writing `sizeof(T*) == 0` makes the expression depend on `T`, deferring the check to instantiation, and a discarded branch is never instantiated.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶2 Some declarations contain scopes of their own, such as class definitions, lambdas and function parameter lists. When Chapter 9 talks about a component of a declaration, it means only the parts not nested within such inner scopes. For example, in `struct A { struct B { } b; } a;` only the class definition of `A` is a component of this declaration; the class definition of `B` belongs to a member declaration in `A`. Otherwise rules of the form "a declaration shall not contain X" would also count the contents of lambda bodies and class bodies.

¶3 A declaration that matches the syntax of a *friend-type-declaration* is treated as a friend type declaration. So `friend C;` is not read as a *simple-declaration* without a declarator; see [[dcl.friend]].

Note 4: the *declarator-id* of a typedef declaration is an identifier, so a typedef can't declare a conversion function name such as `operator int` ([[class.conv.fct]]).

¶16 An empty declaration (a lone `;`) has no effect. So extra semicolons at namespace scope, such as those after `namespace N { };` and `void f() { };`, are well-formed. The C++98 grammar had no empty declaration; these extra semicolons were then accepted only as an extension.

¶17 Unless otherwise specified, the meaning of an attribute declaration (`[[...]];`) is implementation-defined {{impl}}. None of the standard attributes is used in attribute declarations.

</details>
