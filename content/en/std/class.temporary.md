---
title: Temporary objects
summary: "When temporaries are created (since C++17, only when a prvalue has to become an object), when they are destroyed by default (at the end of the full-expression), and the exceptions in seven contexts such as reference binding and range-based for; most of the rules about dangling references live here."
updated: 2026-10-19
---

!!! tldr
    - Since C++17, a prvalue is not an object, just a way of initializing one. A temporary is **materialized** only when an object is required, for example when a reference binds to it. Initializing an object of the same type from a prvalue involves no temporary and needs no copy or move constructor.
    - By default a temporary is destroyed at the end of the full-expression containing it (roughly, a statement), so in `const char* p = name().c_str();`, `p` dangles as soon as the statement ends.
    - When a reference binds directly to a temporary (or a member of one), the temporary lives until the reference's lifetime ends. A reference returned through a function call does not count; this is the most common source of dangling references.
    - Cases that do not extend: binding to a function's reference parameter, parenthesized aggregate initialization, and *new-initializers*. Binding a temporary in a mem-initializer, and in a return statement in C++26, is now simply ill-formed.
    - Since C++23, all temporaries in the initializer of a range-based `for` live until the loop ends.

## When temporaries are created (¶1–¶2)

```cpp run title="guaranteed-elision.cpp" ok
struct NonMovable {
    NonMovable(int) {}
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable(42); }   // OK: the prvalue directly initializes the returned object

int main() {
    NonMovable a = make();                       // OK: no temporary
    NonMovable b = NonMovable(NonMovable(1));    // OK: in the end only b is initialized
    (void)a; (void)b;
}   // in C++14 all three are errors: an accessible copy or move constructor is required
```

Expressions are divided by value category into glvalues and prvalues ([[basic.lval]]). A glvalue refers to an existing object; a **prvalue** is more like a recipe for initializing an object, such as `NonMovable(42)`, `make()` or `1 + 2`. Since C++17 a prvalue is not itself an object; the object it initializes is its **result object**. In the example above, the result object of `make()` is `a`, with no copy in between.

¶1 specifies that a **temporary object** is created in only two cases:

- ¶1.1 when a prvalue is converted to an xvalue, i.e. the **temporary materialization conversion** ([[conv.rval]]);
- ¶1.2 when needed by the implementation to pass or return an object of certain types; see the next section.

Before C++17, every prvalue of class type was a temporary object that was then copied to its destination, and copy elision was merely a permitted optimization. [[P0135R1]] changed this to today's rule, which is guaranteed copy elision.

### Materialization is delayed as long as possible (¶2)

¶2 specifies that materialization is generally delayed as long as possible to avoid creating unnecessary temporaries. Note 2 summarizes the contexts where materialization happens:

| Item | Context | Example |
|---|---|---|
| ¶2.1 | binding a reference to a prvalue | `const T& r = T{};` |
| ¶2.2 | member access on a class prvalue | `T{}.member` |
| ¶2.3 | calling an implicit object member function on a class prvalue | `T{}.f()` |
| ¶2.4 | array-to-pointer conversion or subscripting on an array prvalue | `id<int[3]>{1, 2, 3}[i]` |
| ¶2.5 | initializing `std::initializer_list<T>` from a braced list | `std::initializer_list<int> il = {1, 2, 3};` |
| ¶2.6 | certain unevaluated operands | `sizeof(T{})`, `typeid(T{})` |
| ¶2.7 | a non-`void` prvalue as a discarded-value expression | the expression statement `T{};` |

Initializing an object of the same type from a prvalue does not materialize, as in `T x = T{};`, `return T{};`, and initializing a by-value parameter with `f(T{})`. Here is Example 1 from the standard:

```cpp run title="materialize.cpp" ok
class X {
public:
    X(int) {}
    X(const X&) {}
    X& operator=(const X&) { return *this; }
    ~X() {}
};

X f(X x) { return x; }

int main() {
    X a(1);
    X b = f(X(2));   // X(2) is constructed directly in f's parameter; f's result is constructed directly in b
    a = f(a);        // the result of f(a) must be materialized as a temporary to bind to operator='s const X& parameter
}
```

### Checked even when unevaluated (¶1)

The second sentence of ¶1 specifies that even when the creation of a temporary is unevaluated (for example in `sizeof`), all semantic restrictions are respected as if it were created and later destroyed. Note 1 explains that this includes the accessibility and deletedness of the selected constructor and destructor. The only exception is the operand of `decltype`: a prvalue there introduces no temporary ([[dcl.type.decltype]]).

```cpp run title="unevaluated-temp.cpp" error
struct P { private: ~P(); };
P make();

using A = decltype(make());   // OK: no temporary is introduced in decltype
auto n = sizeof(P{});         // error: the destructor is inaccessible, even though unevaluated
```

## Copying to pass in registers (¶3)

When an object of type `X` is passed to or returned from a function, if `X` is

- ¶3.1 a scalar type, or
- ¶3.2 a class type with at least one eligible copy or move constructor, all of which are trivial, and whose destructor is trivial or deleted,

the implementation may create temporaries to hold the parameter or return object (¶3.3–¶3.5 specify how these temporaries initialize one another in turn). Note 3 explains the motivation: to allow objects to be passed in registers. A register has no address; an object put in a register and written back to memory becomes another object. For such types no user code runs during the copy, so the standard simply allows it.

The observable consequence is that an object's address may differ before and after the call:

```cpp run title="register-pass.cpp" unspecified
#include <cstdio>

struct Small { int a, b; };   // trivially copyable, trivially destructible

const void* seen;

Small make() {
    Small s{1, 2};
    seen = &s;
    return s;                  // may be returned in registers
}

int main() {
    Small r = make();
    std::printf("%d\n", seen == &r);   // unspecified; 0 on AArch64 in our tests
}
```

!!! impl "Non-trivial for the purposes of calls in the ABI"
    The Itanium C++ ABI calls classes that do not satisfy ¶3.2 "non-trivial for the purposes of calls". Such objects cannot be placed in registers; the caller creates them in memory and passes their address. A typical example is `std::unique_ptr<T>`: it is only pointer-sized, but because its destructor is non-trivial it must be passed through memory, costing one more memory round trip than a raw pointer. Clang's `[[clang::trivial_abi]]` lets a class be treated as trivial by the ABI. MSVC x64 has different rules, mainly based on conditions like size (1, 2, 4 or 8 bytes).

## By default, until the end of the full-expression (¶4)

¶4 specifies that a temporary is destroyed as the last step in evaluating the **full-expression** that lexically contains the point where it was created, even if that evaluation ends by throwing an exception. A full-expression is roughly an expression that is not part of another expression ([[intro.execution]]), such as an expression statement, a variable's initializer, or the condition of an `if`. So "a temporary lives until the semicolon" is a good approximation:

```cpp run title="end-of-full-expr.cpp" ok
#include <cstdio>
#include <string>

std::string name() { return "temporary"; }

int main() {
    std::printf("%s\n", name().c_str());   // OK: the temporary string lives until the end of this statement

    const char* p = name().c_str();         // the temporary string is destroyed at this semicolon; p dangles
    (void)p;                                // no UB as long as p is not dereferenced
}
```

Clang 23 gives a `-Wdangling-gsl` warning for the second case.

## Lifetime extension by reference binding (¶6)

### Which bindings extend

```cpp run title="extension-yes.cpp" ok
#include <string>

template<class T> using id = T;
struct S { int m; std::string s; };

int main(int argc, char**) {
    int i = 1;
    const std::string& a = std::string("abc");    // ¶6.1
    int&& b = id<int[3]>{1, 2, 3}[i];             // ¶6.3: the whole temporary array is extended
    std::string&& c = S{1, "x"}.s;                // ¶6.4: the whole S is extended
    const int& d = static_cast<const int&>(0);    // ¶6.6
    int&& e = argc > 1 ? id<int[3]>{1, 2, 3}[i]
                       : static_cast<int&&>(0);   // ¶6.8: only the one actually evaluated is extended
    const int& f = (const int&)1;                 // note 4: a C-style cast is treated as static_cast
    return a.size() + b + c.size() + d + e + f > 0 ? 0 : 1;   // all OK
}
```

¶6 specifies that when a reference binds to a temporary, if the glvalue to which the reference is bound was obtained through one of the following, the temporary (or the complete temporary object containing the subobject the reference binds to) persists for the lifetime of the reference. This is **lifetime extension**.

| Item | Through | Example |
|---|---|---|
| ¶6.1 | a temporary materialization conversion | `const T& r = T{};` |
| ¶6.2 | parentheses `( e )` | `const T& r = (T{});` |
| ¶6.3 | subscripting an array operand | `int&& r = id<int[3]>{1, 2, 3}[i];` |
| ¶6.4 | a class member access using `.` to a non-static data member of non-reference type, or a conversion to a direct base | `int&& r = S{}.m;` |
| ¶6.5 | a pointer-to-member operation using `.*` to a data member of non-reference type | `int&& r = S{}.*pm;` |
| ¶6.6 | one of the four named casts without a user-defined conversion, whose result refers to the same object (or its complete object or a subobject) | `static_cast<const int&>(0)` |
| ¶6.7 | a functional cast to a reference type whose initializer is a braced list | `using R = const T&; R{T{}}` |
| ¶6.8 | a glvalue conditional expression whose second or third operand is one of these expressions | `c ? T{1} : T{2}` |
| ¶6.9 | a glvalue comma expression whose right operand is one of these expressions | `(f(), T{})` |

Except for ¶6.1, each item requires its operand to be one of these expressions too, so the list is recursive. It characterizes a class of expressions whose result can be seen at compile time to be a particular temporary (or a subobject of one); [[stmt.return]] and [[class.base.init]] call them **temporary expressions**.

Note 5 adds that if a reference member of a temporary is initialized by another temporary, extension applies recursively to that member:

```cpp run title="extension-recursive.cpp" ok
struct S { const int& m; };

int main() {
    const S& s = S{1};   // both the S temporary and the int temporary live until s ends
    return s.m;          // OK: 1
}
```

### Going through a function call does not extend

References returned by functions (including member functions and overloaded operators) are not in the ¶6 list. At the call site the compiler cannot tell where the returned reference points, so nothing is extended:

```cpp run title="dangling-call.cpp" ub
#include <algorithm>
#include <string>

struct Holder {
    std::string s{"hello"};
    const std::string& get() const { return s; }
};

int main() {
    const int& m = std::max(1, 2);           // the temporary ints bind to max's reference parameters and live until the semicolon
    const std::string& g = Holder{}.get();   // a member function call, not the member access of ¶6.4
    return m + static_cast<int>(g.size());   // UB: both references dangle
}
```

`Holder{}.s` is a member access and extends the whole `Holder`; `Holder{}.get()` is a function call and does not. Turn a public member into a getter and the reference dangles. Clang 23 gives a `-Wdangling` warning for the `std::max` line and no warning for the `get()` line; AddressSanitizer reports stack-use-after-scope at run time.

### Three bindings that do not extend (¶6.10–¶6.12)

Even when a reference binds directly to a temporary, the following three cases are not extended to the reference's lifetime:

- ¶6.10 A temporary bound to a reference parameter in a function call persists until the end of the full-expression containing the call. The parameter lives shorter than that full-expression anyway, so extension would be pointless.
- ¶6.11 A temporary bound to a reference member when initializing an aggregate of class type from a parenthesized expression list persists until the end of the full-expression containing the list {{c++20}}.
- ¶6.12 A temporary bound to a reference in a *new-initializer* persists until the end of the full-expression containing it. Note 6 points out that this may produce a dangling reference.

<div class="compare" markdown="1">

```cpp run ub
struct A { const int& r; };

int main() {
  A b{42};  // braces: extended until b ends
  A a(42);  // parentheses: ¶6.11, destroyed at the semicolon
  return a.r + b.r;  // UB: reads a.r
}
```

```cpp run ub
#include <utility>
struct S {
  int mi;
  const std::pair<int, int>& mp;
};

int main() {
  S a{1, {2, 3}};           // OK: extended
  S* p = new S{1, {2, 3}};  // ¶6.12
  int r = a.mp.first
        + p->mp.first;      // UB: reads p->mp
  delete p;
  return r;
}
```

</div>

C++20's parenthesized aggregate initialization deliberately imitates a constructor call. If `A` had a constructor `A(const int&)`, the temporary in `A a(42)` would fall under ¶6.10 and not be extended; ¶6.11 keeps aggregates consistent with that.

### Two bindings that are now ill-formed

¶6's list of exceptions used to have two more items, both of which are now ill-formed and must be diagnosed:

1. Binding a reference member to a temporary in a constructor's mem-initializer ([[class.base.init#8]]). The old rule was that the temporary lived until the constructor exited, so the result inevitably dangled. Doing this in a default member initializer is likewise ill-formed ([[class.base.init#13]]), but only when it is actually used for initialization.
2. A return statement binding the returned reference to a temporary ([[stmt.return#6]]) {{c++26}}. In C++23 this was valid but inevitably returned a dangling reference. The change comes from [[P2748R5]].

```cpp run title="now-ill-formed.cpp" error
struct A {
    A() : v(42) {}            // error: a reference member bound to a temporary in a mem-initializer
    const int& v;
};

const int& f() { return 42; }        // error (C++26): the returned reference binds to a temporary
auto&& g() { return 42; }            // error (C++26)
const double& h() {
    static int x = 42;
    return x;                        // error (C++26): converting int to double creates a temporary
}
```

Clang 23 rejects `f`, `g` and `h` under `-std=c++2c` (returning reference to local temporary object), and only warns in `-std=c++23` and earlier modes.

!!! lawyer "The new return rule also recognizes only temporary expressions"
    The example in [[stmt.return]] also contains:

    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f3() { return id(42); }   // OK, but almost certainly a bug
    ```

    `id(42)` is a function call, not a temporary expression, so the new rule does not reach it, for the same reason ¶6 does not extend the result of a function call. `-Wdangling`-style warnings based on annotations like `[[clang::lifetimebound]]` go further in this respect.

## Other exceptional contexts (¶5, ¶7–¶10)

The standard lists seven contexts in all in which temporaries are not destroyed at the end of the full-expression; reference binding is the third. The other six are as follows.

### Default arguments for array elements (¶5)

The first and second contexts: when a default constructor is called to initialize an array element with no corresponding initializer; and when a whole array is copied (for example, a lambda capturing an array by copy, or an implicit copy constructor copying an array member) and elements are copied one by one. In both cases, if the constructor has default arguments, temporaries created in the default arguments are destroyed before the next element is constructed. Otherwise an array of 1000 elements would accumulate 1000 temporaries in one full-expression.

```cpp run title="array-default-arg.cpp" ok
#include <cstdio>

struct Tmp { Tmp() { std::puts("Tmp()"); } ~Tmp() { std::puts("~Tmp()"); } };
struct E { E(const Tmp& = Tmp()) { std::puts("E()"); } };

int main() {
    E arr[2];   // output: Tmp() E() ~Tmp() Tmp() E() ~Tmp()
}
```

### The initializer of a range-based `for` (¶7) {{c++23}}

The fourth context: a temporary created in the *for-range-initializer* of a range-based `for` (the expression right of the colon) that would otherwise be destroyed at its end now persists until the end of the lifetime of the reference it initializes, that is, until the end of the loop.

The definition of range-based `for` contains `auto&& __range = for-range-initializer;` ([[stmt.ranged]]). Under ¶6, the temporary is extended only if the initializer itself is a temporary expression; as soon as a function call intervenes, it dangles:

```cpp run title="range-for.cpp" ok
#include <cstdio>
#include <vector>

struct T {
    std::vector<int> v{1, 2, 3};
    ~T() { std::puts("~T"); }
    const std::vector<int>& items() const { return v; }
};
T make() { return {}; }

int main() {
    for (int x : make().items())   // C++20: the temporary T is destroyed before the loop starts: UB
        std::printf("%d\n", x);    // C++23: the temporary T lives until the loop ends: OK
    std::puts("end");
}
```

Under `-std=c++20`, Clang 23 prints `~T` before entering the loop and reads destroyed data; under `-std=c++23` it prints 1 2 3 and then `~T`. The change comes from [[P2718R0]] and applies only in C++23 and later modes.

### Expansion statements (¶8–¶9) {{c++26}}

The fifth and sixth contexts concern C++26's expansion statements `template for` ([[stmt.expand]]):

- ¶8 In the enumerating form `template for (auto x : {a, b, c})`, a temporary created in an element E of the list that would otherwise be destroyed at the end of E's full-expression now persists until the end of the lifetime of the loop variable initialized by E.
- ¶9 In the iterating and destructuring forms, a temporary created in the initializer that would otherwise be destroyed at the end of the initializer now persists until the end of the lifetime of the reference it initializes (if any).

!!! warning "Implementation status"
    Clang 23 supports `template for`, but these two rules are not yet implemented correctly. In `template for (int y : tup(T{5}))` (where `tup` takes its argument as `const T&` and returns a `std::tuple`), `T{5}` is destroyed before the loop body runs, contrary to ¶9; and writing `{T{7}.v, 8}` in the enumerating form crashes the compiler outright. Don't rely on this extension for now.

### Structured bindings (¶10) {{c++26}}

The seventh context: in a structured binding declaration ([[dcl.struct.bind]]), temporaries introduced by the initializers of the hidden variables with unique names are destroyed only at the end of the whole structured binding declaration. These hidden variables are the references holding the results of `get<i>(e)` in tuple-like bindings. This lets several `get<i>` calls safely share temporaries, with a well-defined point of destruction.

## Order of destruction (¶11–¶12)

¶11 specifies three levels of ordering:

1. Let x and y be two temporaries or function parameters that are not extended. If they are destroyed at the end of the same full-expression and x was initialized before y, then y is destroyed before x.
2. Two or more extended temporaries whose lifetimes end at the same point are destroyed in the reverse order of the completion of their construction.
3. Extended temporaries are also ordered with other objects of the same storage duration: objects of that storage duration created before the temporary are destroyed after it, and those created after it are destroyed before it. In other words, an extended temporary behaves like a variable of the same storage duration defined at its point of creation.

Example 6 in ¶12 demonstrates this:

```cpp run title="destruction-order.cpp" ok
#include <cstdio>

struct S {
    int id;
    S(int i = 0) : id(i) { std::printf("S(%d)\n", id); }
    friend S operator+(const S& a, const S& b) { return S(a.id + b.id); }
    ~S() { std::printf("~S(%d)\n", id); }
};

S obj1(1);
const S& cr = S(16) + S(23);   // S(16) and S(23) bind to reference parameters and are destroyed in reverse order at the semicolon
                               // the result S(39) binds to cr and lives until the end of the program
S obj2(2);

int main() {}
// at program end: ~S(2) → ~S(39) → ~S(1)
```

Which of `S(16)` and `S(23)` is created first is unspecified ([[expr.call]]), but whichever is created first is destroyed last. Clang 23 creates `S(16)` first, and the destruction order printed is `~S(23)`, `~S(16)`.

## Implementation view

!!! impl "How compilers implement lifetime extension"
    - An extended temporary is just a hidden local variable, or a hidden static variable when bound to a static reference: `const T& r = T{};` is roughly equivalent to `T __tmp{}; const T& r = __tmp;`. The Itanium ABI also specifies mangled names for temporaries bound to static references, with the prefix `_ZGR` (reference temporary).
    - Extension is decided at compile time from syntactic structure, so it can never pass through a function call: at the call site the compiler cannot see which object the returned reference refers to. This is the fundamental reason the ¶6 list contains only built-in operations.
    - Clang's `-Wdangling`, `-Wdangling-gsl`, `-Wreturn-stack-address` and the `[[clang::lifetimebound]]` annotation, and GCC's `-Wdangling-reference`, are tools that catch dangling references heuristically, beyond the standard's rules.

## History

!!! history
    - C++98: rvalues of class type produced temporaries in many contexts. The reference extension rule already existed, with exceptions including reference members in constructor initializer lists (lived until the constructor exited), reference parameters of function calls, and return statements (lived until the function exited).
    - C++11: introduced rvalue references and xvalues; the extension rules apply to rvalue references too.
    - C++17: [[P0135R1]] guaranteed copy elision; prvalues are no longer temporaries, and the temporary materialization conversion was introduced. Around the same time, binding a reference member to a temporary in a mem-initializer became ill-formed ([[CWG1696]]).
    - C++20: parenthesized aggregate initialization brought the ¶6.11 exception.
    - C++23: [[P2718R0]] made temporaries in the initializer of a range-based `for` live until the end of the loop.
    - C++26: [[P2748R5]] made binding a returned reference to a temporary in a return statement ill-formed; expansion statements and structured bindings each got rules for destroying temporaries.

## Common misconceptions

!!! pitfall "`std::string_view` can extend temporaries too"
    In `std::string_view sv = std::string("abc");`, `sv` is an object, not a reference, so ¶6 does not apply. The temporary `string` is destroyed at the semicolon, and `sv` dangles. Lifetime extension works only for references.

!!! pitfall "`auto&&` can catch anything"
    `auto&& x = make().value();` goes through a member function call (`std::optional<T>::value()` returns `T&&`), so nothing is extended and `x` dangles. Take it by value instead: `auto x = make().value();`.

!!! pitfall "A `const T&` member can hold on to a temporary"
    In `struct W { const std::string& s; W(const std::string& s) : s(s) {} };  W w(std::string("x"));`, the temporary `string` binds to the constructor's reference parameter (¶6.10) and is destroyed at the semicolon, so `w.s` dangles. `s(s)` binds to the parameter, an lvalue rather than a temporary expression, so the compiler does not diagnose it under [[class.base.init#8]].

## Questions

!!! question "Question 1"
    Which of these references dangle?

    ```cpp
    struct P { int x; int& rx() { return x; } };
    P make();
    const int& a = make().x;                     // (a)
    const int& b = make().rx();                  // (b)
    const int& c = static_cast<P&&>(make()).x;   // (c)
    const int& d = true ? make().x : 0;          // (d)
    ```

<details markdown="1">
<summary>Answer</summary>

(a) Does not dangle: a member access per ¶6.4, and the whole `P` temporary is extended.

(b) Dangles: the result of a member function call is not in the ¶6 list.

(c) Does not dangle: `make()` is materialized (¶6.1), `static_cast<P&&>` involves no user-defined conversion and its result refers to the same object (¶6.6), and then a member access follows (¶6.4).

(d) Does not dangle, but for a different reason. The second operand `make().x` is an xvalue and the third operand `0` is a prvalue; with different value categories, the result of the conditional expression is a prvalue ([[expr.cond]]). So `d` binds to a new temporary `int` materialized from that result (¶6.1), and it is this new object that is extended; the `P` returned by `make()` is destroyed at the semicolon, but `d` does not refer to it.
</details>

!!! question "Question 2"
    Why is `NonMovable x = NonMovable(1);` valid since C++17, while `NonMovable x = std::move(NonMovable(1));` is not?

<details markdown="1">
<summary>Answer</summary>

In the former, the initializer is a prvalue of the same type, with `x` directly as its result object; no copy or move is involved. In the latter, `std::move`'s parameter is a reference, so the argument `NonMovable(1)` must first be materialized as a temporary (¶2.1) to bind to it; `std::move` returns an xvalue, and initializing `x` from an xvalue calls the move constructor, which is deleted. Even for a movable type, writing it this way costs an extra move.
</details>

!!! question "Question 3"
    Does `for (auto& x : std::vector<std::string>{"a", "b"})` dangle in C++20? What about `for (char c : std::string("ab").substr(0))`?

<details markdown="1">
<summary>Answer</summary>

The first does not: `__range` binds directly to the temporary `vector` materialized from the prvalue (¶6.1), which is extended under every standard.

The second does not either: `.substr(0)` returns a new `string` by value, `__range` binds to it, and it is extended. The original `string("ab")` is destroyed at the end of the initializer in C++20, but the loop uses only the result of `substr`. What really dangles is the case where a reference is returned, such as `for (char c : make().name())` (where `name()` returns `const std::string&`), which is UB in C++20 and fine in C++23.
</details>

## Summary

| Question | Rule |
|---|---|
| When created | on materialization; or to pass or return in registers (trivially copyable types) |
| When not created | initializing an object of the same type from a prvalue (guaranteed since C++17) |
| When destroyed by default | as the last step of evaluating the full-expression, the last constructed destroyed first |
| Extended | a reference bound directly to a temporary or a subobject of one through the built-in operations of ¶6.1–¶6.9 |
| Not extended | through a function call; bound to a function's reference parameter (¶6.10); parenthesized aggregate initialization (¶6.11); *new-initializer* (¶6.12) |
| Ill-formed | binding a temporary in a mem-initializer or default member initializer; binding one in a return statement (C++26) |
| Other contexts | default arguments of array elements (¶5); range-based `for` (C++23); expansion statements and structured bindings (C++26) |
