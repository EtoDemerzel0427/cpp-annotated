---
title: Conversions
summary: "How class types take part in implicit conversions: the two kinds of user-defined conversion, converting constructors and conversion functions; at most one per implicit conversion; and how explicit restricts them."
updated: 2026-10-19
---

!!! tldr
    - User-defined conversions come from two sources: a non-explicit constructor converts another type to the class, and a conversion function `operator T()` converts the class to `T`.
    - At most one user-defined conversion is implicitly applied to a single value; it can be preceded and followed by a sequence of standard conversions.
    - Explicit constructors and explicit conversion functions are used only for direct-initialization and explicit conversions. Contextual conversion to `bool`, as in `if (x)`, counts as direct-initialization, so `explicit operator bool` still works in conditions.
    - A conversion function has no parameters and its return type is written after `operator`; it can be virtual and can be a template, but a template can't use an `auto` return type.
    - A conversion function is never used to convert to its own class type, a base class, or `void`.

## User-defined conversions [class.conv.general]

```cpp
struct Meters {
    Meters(double v);              // double → Meters
    operator double() const;       // Meters → double
};
```

Built-in types convert to each other through standard conversions ([[conv]]), such as `int` to `double`. ¶1 Class types specify conversions through constructors and conversion functions, collectively called **user-defined conversions**. They are used for implicit conversions (argument passing, return, assignment and so on), initialization ([[dcl.init]]) and explicit conversions ([[expr.type.conv]], [[expr.cast]], [[expr.static.cast]]). `Meters` above has both directions: the constructor converts from `double`, and the conversion function converts back to `double`.

¶2 User-defined conversions are applied only where they are unambiguous. They obey access control ([[class.access]]), and access is checked after ambiguity resolution. So a private conversion function still takes part in the selection and is reported as inaccessible only after being selected; it isn't silently skipped.

¶3 Note 1 points out that how these conversions are used in function calls is determined by overload resolution ([[over.match]]).

### At most one (¶4)

¶4 At most one user-defined conversion, whether a constructor or a conversion function, is implicitly applied to a single value. Example 1 in the standard:

```cpp title="one-udc.cpp" error
struct X { operator int(); };
struct Y { operator X(); };

Y a;
int b = a;      // error: Y→X→int needs two user-defined conversions
int c = X(a);   // OK: X(a) is an explicit conversion, after which X→int needs only one
```

So an implicit conversion sequence ([[over.best.ics]]) has at most this shape:

```text
standard conversion sequence → one user-defined conversion → standard conversion sequence
```

The restriction has two benefits. Readers don't have to guess how long a chain of types a value went through; and the compiler doesn't have to search for paths between types, only look at the source type's conversion functions and the target type's constructors, and ambiguities are far rarer.

The restriction applies per value. In direct-initialization, the constructor's parameter is itself a new value, and it can use one more user-defined conversion:

```cpp title="udc-per-value.cpp" error
struct A { A(int) { } };
struct B { B(A) { } };

B b1(1);        // OK: B(A) is selected; the argument 1 → A uses one
B b2 = 1;       // error: would need two, int→A→B
void g(B);
void h() {
    g(1);       // error: same as b2
    g(A(1));    // OK: A→B needs only one
}
```

`b1` is direct-initialization: `B`'s constructors take part in overload resolution like ordinary functions ([[over.match.ctor]]), and the argument `1` to the parameter `A` is a separate implicit conversion. `b2` is copy-initialization, which requires a single implicit conversion from `int` straight to `B` ([[over.match.copy]]), and [[over.best.ics#4]] specifically forbids another user-defined conversion on the constructor's argument in that case.

## Converting constructors [class.conv.ctor]

¶1 A constructor that is not explicit specifies a conversion from the types of its parameters to the type of its class. Such a constructor is called a **converting constructor**. Example 1 in the standard:

```cpp run title="converting-ctor.cpp" ok
struct X {
    X(int) { }
    X(const char*, int = 0) { }
    X(int, int) { }
};

void f(X) { }

int main() {
    X a = 1;          // a = X(1)
    X b = "Jessie";   // b = X("Jessie", 0)
    a = 2;            // a = X(2): converts to a temporary first, then assigns
    f(3);             // f(X(3))
    f({1, 2});        // f(X(1, 2)): copy-list-initialization
    (void)b;
}
```

The last line shows that converting constructors aren't limited to a single parameter. Before C++11, only constructors callable with one argument were called converting constructors; with list-initialization, `{1, 2}` can also be implicitly converted to `X`, so every non-explicit constructor counts.

### Explicit constructors (¶2)

¶2 Note 1 says an explicit constructor constructs objects just like a non-explicit one, but does so only where the direct-initialization syntax ([[dcl.init]]) or explicit conversions ([[expr.static.cast]], [[expr.cast]]) are used. A default constructor can also be explicit, and it is used for default-initialization and value-initialization. Example 2 in the standard:

```cpp title="explicit-ctor.cpp" error
struct Z {
    explicit Z();
    explicit Z(int);
    explicit Z(int, int);
};

Z a;                        // OK: default-initialization
Z b{};                      // OK: direct-list-initialization
Z c = {};                   // error: copy-list-initialization
Z a1 = 1;                   // error: no implicit conversion
Z a3 = Z(1);                // OK: Z(1) is an explicit conversion
Z a2(1);                    // OK: direct-initialization
Z* p = new Z(1);            // OK: direct-initialization
Z a4 = (Z)1;                // OK: explicit conversion
Z a5 = static_cast<Z>(1);   // OK: explicit conversion
Z a6 = { 3, 4 };            // error: copy-list-initialization
```

`Z a1 = 1;` and `Z c = {};` fail in different ways. In the copy-initialization `Z a1 = 1;`, explicit constructors aren't candidates at all. In the copy-list-initializations `Z c = {};` and `Z a6 = {3, 4};`, explicit constructors still take part in overload resolution, but if one is selected the program is ill-formed ([[over.match.list]]). With several overloads, this difference can change the outcome: an explicit constructor can win over a non-explicit constructor that would otherwise have been selected, and then cause an error.

The usual practice is to make single-argument constructors `explicit` by default, unless the conversion loses no information and doesn't change meaning, as with `std::string(const char*)`. Implicit converting constructors take part in overload resolution without you noticing:

```cpp title="implicit-danger.cpp" error
#include <vector>

struct Buffer {
    explicit Buffer(std::size_t n) : data(n) { }
    std::vector<char> data;
};

void send(const Buffer&) { }

void use() {
    send(Buffer(1024));   // OK: clear intent
    send(1024);           // error: without explicit, this would quietly allocate 1024 bytes
}
```

### Conditional explicit {{c++20}}

Since C++20 you can write `explicit(constant-expression)` ([[dcl.fct.spec]]), so whether a wrapper type's conversion is explicit can follow the wrapped type. `std::pair`, `std::tuple` and `std::optional` all use it in place of the paired overloads they used to have:

```cpp run title="conditional-explicit.cpp" ok
#include <type_traits>
#include <string>

template<class T>
struct Wrapper {
    T value;
    template<class U>
    explicit(!std::is_convertible_v<U, T>)   // U→T implicit, so Wrapper is too
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

int main() {
    // OK: const char* → std::string is implicit
    Wrapper<std::string> w1 = "hello";
    // OK: direct-initialization
    Wrapper<std::string> w2(std::string_view("hi"));
    // error: string_view → string is explicit
    // Wrapper<std::string> w3 = std::string_view("hi");
    return static_cast<int>(w1.value.size() + w2.value.size()) - 7;
}
```

## Conversion functions [class.conv.fct]

### Declaration form (¶1–¶2)

```text
conversion-function-id:  operator conversion-type-id
conversion-type-id:      type-specifier-seq conversion-declarator(opt)
conversion-declarator:   ptr-operator conversion-declarator(opt)
```

¶1 A function declaration whose name has the form `operator T` declares a **conversion function**. Inside the class it is written plainly as `operator T` (¶1.1); in an out-of-class definition or a friend declaration it must be a qualified name, such as `X::operator int()` (¶1.2).

¶2 A conversion function must be a non-static member function of a class with no non-object parameters. Its return type is the type after `operator`, and no return type may be written in front.

```cpp title="conv-fct-decl.cpp" error
struct X {
    operator int();                   // OK
    explicit operator double() const; // OK
    operator const char*() const;     // OK: the type can contain *
    int operator long();              // error: no return type in front
    operator auto() -> short;         // error: no trailing return type
    static operator char();           // error: must be a non-static member
    operator bool(int);               // error: can't have parameters
};
```

The wording is "no non-object parameters", so since C++23 a conversion function can have an explicit object parameter, as in `operator int(this const X& self)`.

¶3 Example 1 shows that all three forms `int(a)`, `(int)a` and `i = a` call `X::operator int()`.

### Explicit conversion functions (¶4)

¶4 A conversion function can be explicit (since C++11), in which case it is only considered as a user-defined conversion for direct-initialization. A non-explicit conversion function can be used wherever an implicit conversion is needed, not just in assignment and initialization.

```cpp title="explicit-conv-fct.cpp" error
class Y { };
struct Z {
    explicit operator Y() const;
};

void h(Z z) {
    Y y1(z);          // OK: direct-initialization
    Y y2 = z;         // error: not a candidate in copy-initialization
    Y y3 = (Y)z;      // OK: cast
}
```

#### explicit operator bool

The most important use of explicit conversion functions is `explicit operator bool`. The conditions of `if`, `while` and `for`, the operands of `!`, `&&` and `||`, the first operand of `?:` and similar positions [[g:contextually-converted-to-bool|contextually convert the expression to bool]]: if `bool t(e);` is well-formed, its result is used ([[conv.general#4]]). `bool t(e);` is direct-initialization, so explicit conversion functions can be used in these positions:

```cpp title="explicit-bool.cpp" error
struct S {
    explicit operator bool() const { return true; }
};

void use(S s) {
    if (s) { }                  // OK: contextual conversion
    bool b1 = s ? true : false; // OK
    bool b2 = !s;               // OK
    bool b3(s);                 // OK: direct-initialization
    bool b4 = s;                // error: copy-initialization
    int  i  = s + 1;            // error: not converted to bool to take part in arithmetic
}
```

With a non-explicit `operator bool()`, `s + 1`, `s1 == s2` (both sides converted to `bool` and then compared) and `int x = s;` would all compile. The function `g` in Example 2 of the standard shows the same thing: `X` has only a non-explicit `operator int()`, and `(a) ? 1+a : 0`, `(a&&b) ? a+b : i` and `if (a)` call it everywhere. Before C++11, smart pointers had to simulate a safe bool with pointers to members to avoid these surprises; with `explicit operator bool`, that is no longer needed.

### Conversions that never use a conversion function (¶3)

¶3 Note 1 points out that a conversion function is never used to convert an object to its own type (or a reference to it), to a base class (or a reference to it), or to `void`. Each of these conversions has its own mechanism: copy construction, derived-to-base conversion, discarding the value. Such a conversion function can still be declared, and if a base class has a virtual conversion function with the same name, it may be reached through a virtual call.

### Writing the target type (¶5)

¶5 The type after `operator` can't be a function type or an array type. To return a reference to an array or a pointer to a function, define an alias first: `using Arr = int[3]; operator Arr&();`.

¶5 also says the type after `operator` is the longest possible sequence of tokens. Note 2 says this resolves the ambiguity between the declarator `*` and the multiplication operator:

```cpp
&ac.operator int*i;   // syntax error: parsed as &(ac.operator int*) i
                      // not as &(ac.operator int) * i
```

Attributes work the same way: in `operator int [[noreturn]] ();`, `[[noreturn]]` is taken as part of the type `int`, and `noreturn` can't apply to a type, so it is an error.

### Hiding and ambiguity (¶6)

¶6 Note 3 points out that a conversion function in a derived class hides only conversion functions in base classes that convert to the same type. A conversion function's name is `operator T`, so different target types mean different names. A conversion function template whose return type depends on a template parameter hides only the corresponding template in a base class; otherwise it takes part in hiding like a non-template function. Finally, overload resolution ([[over.match.best]]) selects the best conversion function. Example 5 in the standard:

```cpp title="conv-ambiguous.cpp" error
struct X { operator int(); };
struct Y : X { operator char(); };

void f(Y& a) {
    if (a) { }    // error: ambiguous between X::operator int and Y::operator char
}
```

`Y::operator char` doesn't hide `X::operator int`, and both are viable. Converting to `bool`, `int→bool` and `char→bool` are both boolean conversions with the same rank, so the call is ambiguous.

### Virtual conversion functions and conversion function templates (¶7–¶8)

¶7 A conversion function can be virtual:

```cpp run title="virtual-conv.cpp" ok
struct Base {
    virtual operator int() const { return 1; }
    virtual ~Base() = default;
};
struct Derived : Base {
    operator int() const override { return 2; }
};

int main() {
    Derived d;
    const Base& b = d;
    int v = b;           // virtual call to Derived::operator int
    return v - 2;
}
```

A conversion function can also be a template. Its template arguments are deduced from the target type of the conversion ([[temp.deduct.conv]]), which is often used to write a proxy convertible to any type:

```cpp run title="conv-template.cpp" ok
struct Default {
    template<class T>
    operator T() const { return T{}; }
};

int main() {
    int i = Default{};          // T = int
    double d = Default{};       // T = double
    const char* p = Default{};  // T = const char*
    return i + static_cast<int>(d) + (p == nullptr ? 0 : 1);
}
```

¶8 A conversion function template can't have a deduced return type ([[dcl.spec.auto]]). Its template arguments have to be deduced from the target type, while `auto` requires deducing the return type from the function body; the two directions can't both happen. A non-template `operator auto()` is allowed: `struct S { operator auto() { return 1; } };` defines a conversion function to `int`.

```cpp title="conv-template-auto.cpp" error
struct S {
    template<class T>
    operator auto() const { return 1.2; }   // error
};
```

## Implementation view

!!! impl
    In the Itanium ABI, the name part of a conversion function's mangled name is `cv` followed by the target type; for example `X::operator int()` is `_ZN1XcviEv`. Conversion functions to different types are different symbols, which matches ¶6's rule of hiding only those with the same target type.

    When a conversion would need two user-defined conversions, Clang only reports `no viable conversion from 'Y' to 'int'` without saying why. When you see this error, check whether one of the steps needs to be written as an explicit `X(a)`.

## History

!!! history
    - C++98 already had converting constructors, explicit constructors, conversion functions and conversion function templates, as well as the limit of at most one user-defined conversion.
    - C++11 introduced explicit conversion functions and contextual conversion to bool; list-initialization made non-explicit constructors with several parameters converting constructors too.
    - Since C++14, non-template conversion functions can use an `auto` return type.
    - C++20 introduced `explicit(bool)`.
    - Since C++23, conversion functions can have an explicit object parameter ([[P0847R7]]).

## Common misconceptions

!!! pitfall "`f(\"hi\")` calls `f(std::string)`"
    Given `void f(std::string); void f(bool);`, `f("hi")` selects `f(bool)`. Pointer to `bool` is a standard conversion, which beats the user-defined conversion from `const char*` to `std::string`.

!!! pitfall "explicit prevents all implicit uses"
    `explicit operator bool` is still called in `if`, `!` and `&&`. An explicit constructor still takes part in overload resolution in copy-list-initialization, and is an error if selected.

!!! pitfall "Providing conversions in both directions"
    If `A` has `A(const B&)` and `B` has `operator A() const`, then `A a = b;` is ambiguous: both candidates bind the argument to `const B&`. Drop the `const` and, when `b` is a non-const lvalue, the conversion function is selected, because binding to `B&` beats binding to `const B&`; the result then depends on the argument's cv-qualification, which is just as undesirable. Define conversions between a pair of types in one direction only.

## Questions

!!! question "Question 1"
    ```cpp
    struct A { A(int); };
    struct B { operator int(); };
    void f(A);
    void g() { B b; f(b); }
    ```
    Is `f(b)` valid?

<details markdown="1">
<summary>Answer</summary>

No. `b` to `A` would need two user-defined conversions, `B::operator int` and `A::A(int)`, violating [class.conv.general] ¶4. `f(A(b))` works: in the direct-initialization `A(b)`, `b` to the constructor parameter `int` uses only one user-defined conversion.
</details>

!!! question "Question 2"
    Is `struct X { operator X&(); operator void(); };` valid? When would these two functions be called?

<details markdown="1">
<summary>Answer</summary>

The declarations are valid, and Clang warns that they will never be used. By ¶3 note 1, a conversion function is never used to convert to a reference to its own type or to `void`: `X& r = x;` binds directly, and `(void)x` discards the value. They can only be called explicitly, as in `x.operator X&()`, or reached through a virtual call when they override a virtual conversion function of a base class.
</details>
