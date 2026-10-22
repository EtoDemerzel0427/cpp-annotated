---
title: References
summary: "What the reference declarators `&` and `&&` mean: references are not objects, so there are no references to references, arrays of references or pointers to references; references can't carry cv; which references may be left uninitialized; which bindings are undefined behavior; and reference collapsing and forwarding references."
updated: 2026-10-19
---

!!! tldr
    - A reference can be thought of as another name for an object or function. It is not an object, and whether it occupies storage is unspecified, so there are no references to references, arrays of references or pointers to references.
    - Writing `int& const` directly is ill-formed; cv added to a reference through an alias or `decltype` is ignored, so `typedef int& A; const A` is still `int&`.
    - A reference must be initialized; the only exceptions are `extern` declarations, class member declarations, parameters and return types.
    - Binding a reference to the result of dereferencing a null pointer, to an object of the wrong type, or using a reference before it is initialized, is undefined behavior.
    - References to references formed through aliases, template parameters or `decltype` collapse: if either is `&`, the result is an lvalue reference. Forwarding references `T&&` work by this rule.

How a reference binds to its initializer (direct binding, temporary materialization, lifetime extension) is in [[dcl.init.ref]]; value categories as they relate to references are in [[basic.lval]] and [[topics/value-categories]].

## Reference declarators (¶1–3)

```cpp run ok
struct link { link* next; };
link* first;

void h(link*& p) {     // p is a reference to a pointer
  p->next = first;
  first = p;
  p = nullptr;         // modifies the caller's pointer
}

int v[20];
int& g(int i) { return v[i]; }

int main() {
  link* q = new link;
  h(q);                // afterwards q is null and first points to the original node
  g(3) = 7;            // assigns to v[3]
  bool ok = q == nullptr && v[3] == 7;
  delete first;
  return ok ? 0 : 1;
}
```

The example in ¶3 shows three typical uses of references: as a parameter so a function can modify its argument, as a return value so `g(3) = 7` assigns to an array element, and a reference to a pointer `link*&` so a function can modify the caller's pointer.

¶1 If `D` in a declaration `T D` has the form `& D1` or `&& D1`, the type of the name is "reference to `T`", preceded by the modifiers accumulated by the inner declarator (see [[dcl.decl]]). Attributes can follow `&` and appertain to the reference type. Note 1 gives a way to think about references: a reference can be thought of as a name of an object.

¶2 A reference declared with `&` is an **lvalue reference** ([[g:lvalue-reference|lvalue reference]]), and one declared with `&&` is an **rvalue reference** ([[g:rvalue-reference|rvalue reference]]). They are distinct types; except where explicitly noted, they are semantically equivalent and commonly called references. The explicitly noted places are the rules that C++11 move semantics relies on:

| Difference | Subclause |
|---|---|
| An rvalue reference can only bind to rvalues (and function lvalues); a non-const lvalue reference can only bind to lvalues | [[dcl.init.ref]] |
| In overload resolution, an rvalue argument prefers binding to an rvalue reference | [[over.ics.rank]] |
| A function call returning an rvalue reference, or an expression converted to an rvalue reference, is an xvalue | [[basic.lval]] |
| A named rvalue reference variable is itself an lvalue | [[expr.prim.id.unqual]] |

!!! pitfall "A named rvalue reference is an lvalue"
    In `void f(std::string&& s) { g(s); }`, `g(s)` calls the overload taking an lvalue, not `g(std::string&&)`. To keep moving, write `g(std::move(s))`.

## References can't carry cv (¶1)

In the grammar of ¶1, no cv-qualifiers can follow `&`; this differs from pointers.

!!! std
    Cv-qualified references are ill-formed except when the cv-qualifiers are introduced through the use of a *typedef-name* or *decltype-specifier*, in which case the cv-qualifiers are ignored.

```cpp run error
int i;
int& const cr = i;   // error: cv can't be added to a reference directly

typedef int& A;
const A ar = i;      // OK: const is ignored, and ar has type int&
const A aref = 3;    // error: aref is int& and can't bind to an rvalue
```

The last line is Example 1 in the standard. People often assume `const A` is `const int&`, but the `const` qualifies the reference type `A` itself, and references can't have cv, so the `const` is dropped. Clang gives a `-Wignored-reference-qualifiers` warning for this.

Why isn't it an error through an alias? In a template, the `T` in `const T` may be substituted with a reference type. If that were an error, lots of generic code would need special handling for references. A reference can't be reseated anyway, so ignoring cv doesn't contradict its semantics. Writing `int& const` directly, on the other hand, almost certainly comes from a misunderstanding, and an error corrects it promptly.

The last sentence of ¶1 says that forming a "reference to cv `void`" is ill-formed:

```cpp run error
template<class T> T& deref(T* p) { return *p; }
void g(void* p) { deref(p); }   // error: T deduces void, void& is invalid, no viable function
```

¶8 is a note: function types with cv- or ref-qualifiers (such as `void() const`) can't form references either; see [[dcl.fct#11]].

## References are not objects (¶4–5)

¶4 It is unspecified whether a reference requires storage. A local `int& r = x;` is usually optimized into an alias for `x` that takes no space; data members of reference type, lambda members capturing by reference, and reference parameters that aren't inlined are in practice implemented as pointers.

```cpp run ok
struct R { int& r; };
static_assert(sizeof(R) == sizeof(void*));   // holds on mainstream implementations; not guaranteed by the standard
int main() { }
```

Since a reference doesn't necessarily have storage and isn't an object, many things simply make no sense for it.

¶5 says:

!!! std
    There shall be no references to references, no arrays of references, and no pointers to references.

```cpp run error
int x;
int& && rr = x;   // error: reference to reference (when written directly; through an alias it collapses, see below)
int& arr[2];      // error: array of references
int&* pr;         // error: pointer to reference
int& noinit;      // error: a reference must be initialized
```

When you need a reseatable reference or an array of references, use pointers or `std::reference_wrapper<T>`. The latter is an object that stores a pointer internally.

### Must be initialized, with three exceptions (¶5)

The second half of ¶5 says a reference declaration must have an initializer ([[dcl.init.ref]]), except in the following three cases, all of which are initialized elsewhere:

```cpp run ok
extern int& ext;                         // 1. explicitly extern: defined elsewhere
struct M {
  int& m;                                // 2. member in a class definition: initialized by the constructor
  M(int& x) : m(x) { }
};
int& pick(int& a, int&) { return a; }    // 3. parameters and return types: initialized by the call
int g = 0;
int& ext = g;
int main() { M m(g); return pick(m.m, ext); }
```

## Undefined behavior when binding (¶6)

¶6 has three kinds of undefined behavior in total. Example 3 in the standard puts them together:

```cpp
int &f(int&);
int &g();
extern int &ir3;
int *ip = 0;
int &ir1 = *ip;     // UB: null pointer
int &ir2 = f(ir3);  // UB: ir3 not yet initialized
int &ir3 = g();
int &ir4 = f(ir4);  // UB: ir4 used in its own initializer

char x alignas(int);
int &ir5 = *reinterpret_cast<int *>(&x);   // UB: the initializer designates a char object
```

### Binding to an object or function of the wrong type

First: when a reference is bound to a function, if the initializer (after conversions) is a glvalue whose type is not call-compatible ([[expr.call]]) with the type of the function's definition, the behavior is undefined. The typical way to get here is a `reinterpret_cast` to the wrong function type first:

```cpp run ub
void f(int) { }
using F = void(long);
int main() {
  F& r = reinterpret_cast<F&>(f);   // UB: void(int) and void(long) are not call-compatible
  (void)r;
}
```

Second: when a reference is bound to an object, if the object is not type-accessible through the type of the initializer glvalue (i.e. the strict aliasing rule, see [[basic.lval]]), the behavior is undefined. The `ir5` above is such a case: `x` is a `char` object and can't be accessed through a glvalue of type `int`. Note that the undefined behavior happens at binding time; there's no need to wait for a read or write.

### There are no null references

Note 2 explains that the object a glvalue designates may be outside its lifetime ([[basic.life]] allows such binding in some cases, e.g. during construction). But a null pointer value or a past-the-end pointer doesn't point to an object at all, so in a well-defined program a reference can't refer to them.

This is the basis for "there are no null references". If `p` is null, `*p` is already undefined behavior ([[expr.unary.op]]), and what you get is not an object at all. UBSan can catch such a binding at run time:

```cpp run ub
#include <cstdio>
int* ip = nullptr;
int main() {
  int& r = *ip;                     // UB: binds to the result of dereferencing a null pointer
  std::printf("%p\n", (void*)&r);
}
```

Compiled and run with `-fsanitize=undefined`, it reports reference binding to null pointer of type 'int'.

Because this is undefined behavior, the compiler may assume a reference is never null. `if (&r == nullptr)` can be optimized straight to `false`, and Clang gives a `-Wtautological-undefined-compare` warning for it. Note 2 also mentions that a reference can't bind directly to a bit-field ([[class.bit]]); when a `const int&` binds to a bit-field, it binds to a materialized temporary.

### Using a reference before it is initialized

Third: if an evaluation of a reference does not happen after its initialization (happens after, [[intro.races]]), the behavior is undefined.

In the example, `ir4` uses itself in its own initializer, and Clang gives a `-Wuninitialized` warning (reference 'ir4' is not yet bound to a value when used within its own initialization). `ir2` is the static initialization order problem ([[basic.start]]) showing up for references: `ir3` is dynamically initialized with `g()`, and before that it isn't bound to anything; using it then doesn't give zero but undefined behavior.

## Reference collapsing (¶7)

Writing `int& &` directly is ill-formed, but a reference to a reference formed indirectly through a type alias, a template type parameter or `decltype` is allowed and yields a single reference by the rules of **reference collapsing** ([[g:reference-collapsing|reference collapsing]]):

```cpp run ok
#include <type_traits>
int i;
typedef int&  LRI;
typedef int&& RRI;

LRI& r1 = i;            // int&
const LRI& r2 = i;      // int& (const ignored)
const LRI&& r3 = i;     // int&
RRI& r4 = i;            // int&
RRI&& r5 = 5;           // int&&
decltype(r2)& r6 = i;   // int&
decltype(r2)&& r7 = i;  // int&

static_assert(std::is_same_v<decltype(r3), int&>);
static_assert(std::is_same_v<decltype(r5), int&&>);
static_assert(std::is_same_v<decltype(r7), int&>);
int main() { (void)r1; (void)r4; (void)r6; }
```

¶7 Let the type `TR` denoted by an alias or `decltype` be a reference to `T` (`T&` or `T&&`). An attempt to form "lvalue reference to cv `TR`" yields `T&`; an attempt to form "rvalue reference to cv `TR`" yields `TR` itself. In both cases cv is ignored.

| Alias `TR` | Add `&` | Add `&&` |
|---|---|---|
| `T&` | `T&` | `T&` |
| `T&&` | `T&` | `T&&` |

A way to remember it: if either is `&`, the result is `&`; only when both are `&&` do you get `&&`.

### Forwarding references

The main use of reference collapsing is perfect forwarding. [[temp.deduct.call#3]] defines a **forwarding reference** ([[g:forwarding-reference|forwarding reference]]): in a function template parameter, an rvalue reference `T&&` to a cv-unqualified template type parameter. During class template argument deduction, if `T` is a parameter of the class template itself, `T&&` is not a forwarding reference. `auto&&` is also a forwarding reference.

During deduction, if the argument is an lvalue, `T` is deduced as the lvalue reference type `U&`, so the parameter type `T&&` is `U& &&`, which collapses to `U&`. If the argument is an rvalue, `T` is deduced as `U` and the parameter type is `U&&`.

```cpp run ok
#include <type_traits>

template<class T> void f(T&& t) {       // forwarding reference
  if constexpr (std::is_lvalue_reference_v<T>)
    static_assert(std::is_lvalue_reference_v<decltype(t)>);
  else
    static_assert(std::is_rvalue_reference_v<decltype(t)>);
}
template<class T> void g(const T&&);    // not a forwarding reference: has const
template<class T> struct W {
  void m(T&&);                          // not a forwarding reference: T isn't deduced here
};

int main() {
  int i = 0;
  const int ci = 0;
  f(i);       // T = int&, parameter int&
  f(ci);      // T = const int&, parameter const int&
  f(1);       // T = int, parameter int&&

  auto&& a = i;   // int&
  auto&& b = 1;   // int&&
  static_assert(std::is_same_v<decltype(a), int&>);
  static_assert(std::is_same_v<decltype(b), int&&>);
}
```

`std::forward<T>(t)` is implemented as `static_cast<T&&>(t)`. With `T = U&` it collapses to `U&` and the result is an lvalue; with `T = U` it is `U&&` and the result is an xvalue. This restores the value category of the original argument. The common range-for idiom `for (auto&& e : r)` relies on this too: it handles iterators that return references as well as those that return values.

!!! pitfall "The `T` in `const T&` is a reference"
    For `template<class T> void f(const T& x)`, if `T` is explicitly specified as `int&`, the parameter type is `int&`, not `const int&`: the `const` added to a reference is ignored, and then collapsing happens. An argument that shouldn't be modified becomes modifiable.

## Implementation notes

!!! impl
    - In the Itanium C++ ABI, reference parameters are passed the same way as pointer parameters, by address; data members of reference type have the same layout as pointers. Name mangling distinguishes them: an lvalue reference is `R` and an rvalue reference is `O`, e.g. `_Z1hRi` is `h(int&)` and `_Z1hOi` is `h(int&&)`.
    - Compilers treat references as non-null, aligned, dereferenceable pointers. Clang adds `nonnull`, `dereferenceable(N)` and `align` attributes to reference parameters in LLVM IR; this is exactly the optimization room left by the undefined behavior in paragraph 6.

## History

!!! history
    - C++98 had only lvalue references. A reference to a reference was ill-formed in all cases, so `T&` in a template broke when `T = int&`, and adapters such as `std::bind1st` couldn't handle function objects taking reference parameters.
    - C++11 added rvalue references and move semantics ([[N2118]] and other proposals), the full reference collapsing rules, and the deduction rule later called forwarding references.
    - Wording after C++23 describes the undefined behavior of paragraph 6 precisely in terms of call-compatibility and type-accessibility, replacing the earlier vague statement that "a reference shall be initialized to refer to a valid object or function".
    - Since C++26, binding a returned reference to a temporary in a `return` statement is ill-formed ([[stmt.return]]).

## Questions

!!! question "Question 1"
    Given `template<class T> using Ref = T&;`, what are the types of the variables below?
    ```cpp
    int i;
    Ref<int&&> a = i;
    Ref<const int>&& b = i;
    const Ref<int> c = i;
    decltype((i))&& d = i;
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: `Ref<int&&>` is "lvalue reference to `int&&`", which collapses to `int&`.
- `b`: `Ref<const int>` is `const int&`; adding `&&` collapses to `const int&`.
- `c`: `Ref<int>` is `int&`; the `const` added to the reference through the alias is ignored, so the type is `int&`.
- `d`: the parenthesized name `(i)` is an lvalue, `decltype((i))` is `int&`, and adding `&&` collapses to `int&`.
</details>

!!! question "Question 2"
    `int* p = nullptr; int& r = *p;` is undefined behavior. What about `sizeof(*p)` and `decltype(*p)`?

<details markdown="1">
<summary>Answer</summary>

Both are fine. The `*p` in `sizeof(*p)` and in `decltype(*p)` is an unevaluated operand ([[expr.sizeof]], [[dcl.type.decltype]]), so nothing is actually dereferenced. The former yields `sizeof(int)`, the latter the type `int&`.
</details>
