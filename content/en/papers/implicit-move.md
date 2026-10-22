---
title: Simpler implicit move (P1825, P2266)
summary: When return x; moves instead of copying. From C++11's two-stage overload resolution borrowed from the copy elision conditions, through the gradual relaxations of CWG1579 and P1825, to C++23's P2266 making the returned name an xvalue outright, and which code changed meaning at each step.
tags: implicit move, value categories, xvalue, copy elision, return, proposal
group: Core language
updated: 2026-10-19
---

!!! tldr
    - Implicit move means that `return x;` and `throw x;` move the local variable `x` without writing `std::move`. It covers the initialization that remains when copy elision does not happen.
    - From C++11 to C++20 the rule was two-stage overload resolution: first resolve with `x` as an rvalue, and if that fails, resolve again with it as an lvalue. CWG1579 and P1825 only kept widening where the first stage applies.
    - C++23's P2266 removed the two stages: in the operand of `return`, `co_return` and `throw`, a name denoting an implicitly movable entity is itself an xvalue, and overload resolution happens only once.
    - The cost is that a batch of old code changes meaning: `int& f(int&& x) { return x; }` becomes ill-formed, and `decltype(auto)` with `return (x);` deduces `T&&`. These incompatibilities were explicitly accepted and recorded in Annex C.
    - Implementations apply P1825 as a defect report to all older modes; P2266 is not a defect report, and Clang only enables it from `-std=c++23` on.

## Five outcomes for the same `return x;`

Each of these functions just writes `return name;`. `W` is a class with copy and move constructors, and `Der` derives publicly from `W`:

| Function | C++11 original wording | With CWG1579 | C++20 (P1825) | C++23 (P2266) |
|---|---|---|---|---|
| `W f() { W w; return w; }` | Move | Move | Move | Move |
| `unique_ptr<B> f() { unique_ptr<D> p; return p; }` | Ill-formed | Move | Move | Move |
| `W f() { Der d; return d; }` | Copy | Copy | Move | Move |
| `W f(W&& r) { return r; }` | Copy | Copy | Move | Move |
| `void f(W w) { throw w; }` | Copy | Copy | Move | Move |
| `W&& f(W&& r) { return r; }` | Ill-formed | Ill-formed | Ill-formed | Well-formed |
| `int& f(int&& r) { return r; }` | Well-formed | Well-formed | Well-formed | Ill-formed |

The move in the first row can also be removed by copy elision (NRVO); the table only says which constructor is used when it is not elided. Every cell is determined by the standard wording of its time, explained step by step below.

Today's compilers only show part of this: CWG1579 and P1825 are treated as defect reports, and Clang 23 already moves per the C++20 rules under `-std=c++11`; only the last two rows change between `-std=c++20` and `-std=c++23`.

First, separate two mechanisms that often get mixed up. **Copy elision** ([[g:copy-elision|copy elision]]) decides whether an initialization can be omitted entirely; see [[class.copy.elision#1]] and [[papers/guaranteed-copy-elision]]. **Implicit move** decides, when that initialization is not omitted, whether the source object is treated as an lvalue or an rvalue, and therefore whether the copy or the move constructor is chosen. This page is about the latter.

## C++11: borrowing the copy elision conditions

After C++11 introduced rvalue references, returning move-only types (such as `std::unique_ptr`) by value needed `return p;` to move automatically, or else `std::move` would have to be written everywhere. C++11's rule was written into the copy elision paragraph (then [class.copy]/32). In outline:

1. If the conditions for copy elision are met, or would be met except that the source object is a function parameter, overload resolution to select the constructor is first performed as if the source object were an rvalue;
2. If that resolution fails, or the first parameter of the selected constructor is not an rvalue reference to the object's type, overload resolution is performed again with the object as an lvalue.

This is **two-stage overload resolution**. The second stage is a safety net: when resolution as an rvalue finds no suitable move constructor, it falls back to C++03 behavior, and code that used to compile still selects the copy constructor.

The problem is that step 1 borrows the copy elision conditions, and NRVO requires the returned object to have the same type as the return type (ignoring cv). As soon as the types differ, implicit move does not happen:

```cpp title="cwg1579.cpp" run std=c++11 ok
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};

std::unique_ptr<B> f() {
  std::unique_ptr<D> p(new D);
  return p;   // C++11 original wording: p is an lvalue,
}             // can only be copied, and unique_ptr is not copyable
int main() { return f() ? 0 : 1; }
```

The converting constructor of `unique_ptr<B>` accepts `unique_ptr<D>&&`, which an lvalue cannot bind to; the copy constructor is deleted. Under the original C++11 wording this function is ill-formed, and the programmer must write `return std::move(p);`.

### CWG1579: no longer the same type

[[CWG1579]] made the condition independent of copy elision: as long as the operand of `return` is a (possibly parenthesized) *id-expression* naming an object with automatic storage duration declared in the function body or parameter list, it is first resolved as an rvalue. Then `optional<T> f() { T t; return t; }` can use `optional(T&&)`, and the `unique_ptr` example above becomes a move. It was merged into C++14 as a defect report, and Clang 23 accepts the program above already under `-std=c++11`.

But the restriction in step 2 stayed as it was: the first parameter of the selected constructor must be an rvalue reference to the object's type, otherwise it still falls back to an lvalue. So in `W f() { Der d; return d; }` the first stage selects `W(W&&)`, whose parameter is `W&&` rather than `Der&&`; it is judged unsuitable, and after resolving again it copies.

## C++20: P1825 fills four gaps

[[P1825R0]] itself is just wording, merging two separately adopted proposals: [[P0527R1]] and [[P1155R3]]. They relax the rules from two directions.

### Variables of rvalue reference type (P0527)

```cpp title="rref.cpp" run ok
#include <memory>
std::unique_ptr<int> f(std::unique_ptr<int>&& p) {
  return p;   // moves since C++20; before that p is a reference, not an object, so it can only copy
}
int main() { return *f(std::make_unique<int>(0)); }
```

Before C++20, implicit move applied only to objects; `p` is a reference and did not qualify, so the function above was ill-formed. P0527's reasoning: an rvalue reference variable is either bound to a prvalue (a temporary object), or the caller explicitly wrote a conversion such as `std::move`; either way, the caller has already agreed to it being moved from. For this it introduced the term **implicitly movable entity** ([[g:implicitly-movable-entity|implicitly movable entity]]): a variable of automatic storage duration that is either a non-volatile object or an rvalue reference to a non-volatile object type.

P0527 also unified `throw` with `return`: function parameters and `catch` clause parameters can be implicitly moved in `throw` as well. The old wording excluded them because they cannot undergo copy elision.

This relaxation is observable by the caller. When the callee does `return s;`, the caller's object is hollowed out:

```cpp title="consume.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

std::string consume(std::string&& s) {
  return s;   // moves, not copies
}

int main() {
  std::string s(100, 'x');
  std::string t = consume(std::move(s));
  std::printf("%zu %zu\n", t.size(), s.size());
}
```

Clang 23 (libc++) prints `100 0` under every mode from `-std=c++11` to `-std=c++23`. `s` is in a valid but unspecified state, and libc++ empties it. Annex C's [[diff.cpp17.class#3]] gives the same example with a custom type: the moved-from pointer member becomes null, and the caller's previously valid dereference becomes undefined behavior.

### Removing the first-parameter restriction (P1155)

P1155 lists four counterintuitive copies under the C++17 wording and identifies which word of the original wording causes each:

| Code | C++17 wording | Cause |
|---|---|---|
| `void f(W w) { throw w; }` | Copy | `throw` excluded function parameters |
| `W f() { To t; return t; }`, `To` has `operator W() &&` | Copy | Only constructors are considered, not conversion functions |
| `Fowl f() { W w; return w; }`, `Fowl(W)` takes by value | Copy | The parameter is not an rvalue reference |
| `W f() { Der d; return d; }` | Copy | The parameter is not an rvalue reference to the object's type |

P1825 deleted the entire sentence in step 2 about the first parameter. From then on the rule is: the first stage resolves with the operand as an rvalue, and as long as resolution succeeds its result is used, whether it selects a conversion function, a constructor taking its parameter by value, or a base class's move constructor; only if the first stage fails does it fall back to an lvalue.

```cpp title="more-moves.cpp" run std=c++20 ok
#include <cstdio>
struct W {
  W() {}
  W(const W&) { std::puts("copy"); }
  W(W&&) { std::puts("move"); }
};
struct Der : W {};
struct Fowl { Fowl(W) {} };
struct To {
  operator W() const& { std::puts("conv&"); return W(); }
  operator W() && { std::puts("conv&&"); return W(); }
};

W    slice() { Der d; return d; }
Fowl sink()  { W w; return w; }
W    conv()  { To t; return t; }

int main() { slice(); sink(); conv(); }
```

Clang 23 prints `move`, `move`, `conv&&` under every mode from `-std=c++11` to `-std=c++2c` (the `return W();` in `conv&&` is a prvalue and produces no further move). Implementations applied P1825 as a defect report to all language modes, so the behavior of the original C++17 wording can no longer be seen in today's compilers.

This step also has an incompatibility: if the base class's move constructor is private, `return d;` selects it in the first stage, access checking fails, and the program becomes ill-formed, whereas in C++17 it would fall back to the accessible copy constructor. This is recorded in [[diff.cpp17.class#3]].

## What C++20 still left

After P1825 the rule was still two rounds of overload resolution, and it only took effect when initializing the returned object. [[P2266R3]] starts from these two points to list the remaining problems.

### Functions returning references get no implicit move

The two-stage rule is written in the copy elision section and is about which constructor to choose. When the return type is a reference no constructor is called at all, the rule does not apply, and the name is still an lvalue:

```cpp title="backwarding.cpp" run std=c++23 ok
struct W {};

template<class T>
T&& seven(T&& x) { return x; }   // with T = W: C++20 error

W&& four(W&& w) { return w; }    // C++20 error, C++23 OK

int main() {
  W w;
  W& r = seven(w);
  W&& rr = seven(static_cast<W&&>(w));
  (void)r; (void)rr; (void)four;
}
```

In C++20 the return type `W&&` of `four` cannot bind to the lvalue `w`. The same `w` is treated as an rvalue when the return type is `W`, but as an lvalue when the return type is `W&&`. This is especially awkward in templates: `seven` wants to return a forwarding reference as-is, and fails to compile when `T` is deduced as `W`. Clang 23 reports rvalue reference to type 'W' cannot bind to lvalue of type 'W' for both under `-std=c++20`, and accepts them under `-std=c++23`.

Conversion functions have the same inconsistency: `operator int*() &&` can be used by `return x;`, but `operator int&() &&` cannot, because the latter initializes a reference return value.

### Oddities caused by resolving twice

The author of P2266 points out that, to the author's knowledge, this is the only place in the language that performs overload resolution twice on the same operand, and the results are sometimes counterintuitive:

- With `Sam(W&)` and `Sam(const W&)` both present, the first stage of `return w;` treats `w` as an rvalue, only `const W&` is viable, and so it is selected. Resolving as an lvalue would have chosen the better `Sam(W&)`.
- With `Frodo(W&)` and `Frodo(W&&) = delete` both present, the first stage selects the deleted function. Does that count as resolution succeeding (followed by an error) or failing (falling back to an lvalue)? By [[over.match.general#3]], resolution succeeds as long as there is a unique best viable function, whether or not it is deleted; it is using the deleted function afterwards that is ill-formed ([[dcl.fct.def.delete#2]]). The paper records that compilers at the time were not consistent here.
- With `Quest(Merry&&)`, `Quest(Pippin&&)` and `Quest(Together&)`, returning a local of type `Together`, which derives from both `Merry` and `Pippin`: the first stage is ambiguous, which counts as failure, and the second stage silently selects `Quest(Together&)`.

The most dangerous is `std::reference_wrapper`:

```cpp title="refwrap.cpp" run std=c++20
#include <functional>
std::reference_wrapper<int> f() {
  int i = 0;
  return i;   // C++20: well-formed, returns a dangling reference; C++23: error
}
int main() {}
```

The constructor of `reference_wrapper` is constrained not to accept rvalues precisely so that it cannot bind to temporaries ([[LWG2993]]). Under the two-stage rule, the first stage finds no viable function, which counts as failure; the second stage treats `i` as an lvalue, binds successfully, and returns a wrapper referring to a destroyed local variable. Clang 23 gives no warning at all for this under `-std=c++20 -Wall`; under `-std=c++23` it reports the error no viable conversion.

## The design space

There are three ways to address these problems.

**Just patch the holes.** Extend the two-stage rule to the initialization of references, so `four` and `seven` compile. This fixes the most obvious defect, but the double resolution and the `Sam`, `Frodo`, `Quest` and `reference_wrapper` problems it brings all remain, and compilers' different interpretations of resolution failure would persist.

**Invent a new value category.** P2266 mentions that after P1825 was adopted, the core group discussed problems like `Sam` internally, and concepts were floated along the lines of an lvalue that prefers to bind to rvalue references, or an rvalue that reluctantly binds to lvalue references. According to the paper, that discussion reached no conclusion, only the consensus that all of these were worse than the status quo. The reason is easy to see: there are already five value categories, and adding a half-lvalue, half-rvalue category that only appears in `return` would only make the rules harder to understand.

**Make the name an xvalue outright.** This is P2266's approach. In the operand of `return` and `co_return` and the operand of `throw`, an *id-expression* denoting an implicitly movable entity is itself an xvalue ([[g:xvalue]]), called **move-eligible** ([[g:move-eligible]]). Everything afterwards proceeds as usual, with only one round of overload resolution: when initializing the returned object it selects the move constructor just like `std::move(x)`; when the return type is `W&&` it can bind to it; when the return type is `int&` it cannot.

The third path buys a rule that can be stated on its own: the value category is determined by the context of the expression, and subsequent overload resolution, reference binding and `decltype` no longer need to know that implicit move exists. The cost is that all code depending on the returned name being an lvalue changes meaning:

<div class="compare" markdown="1">

```cpp title="Well-formed in C++20"
int& g(int&& x) {
  return x;   // lvalue binds to int&
}

struct Weird {
  Weird();
  Weird(Weird&);
};
Weird h() {
  Weird w;
  return w;  // second stage: Weird(Weird&)
}
```

```cpp title="Ill-formed in C++23"
int& g(int&& x) {
  return x;   // an xvalue can't bind to int&
}

struct Weird {
  Weird();
  Weird(Weird&);
};
Weird h() {
  Weird w;
  return w;  // an xvalue can't bind to Weird&
}
```

</div>

The first pair corresponds directly to the example in [[diff.cpp20.expr#1]]. The second is the standard's own example in [[class.copy.elision#3]], where `Weird`'s copy constructor only accepts a non-const lvalue reference. Under `-std=c++23`, Clang 23 reports non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int' for `g` (`x` is not actually a temporary; the diagnostic wording is inaccurate), and no matching constructor for `h`.

Deduction for `decltype(auto)` changes as well. It treats the operand of `return` as the operand of `decltype` ([[dcl.type.auto.deduct#4]]), and the parenthesized `decltype((e))` reflects the value category of `e`:

```cpp title="decltype-auto.cpp" run std=c++23 ok
#include <type_traits>
decltype(auto) f(int&& x) { return (x); }
decltype(auto) g(int x)   { return (x); }

static_assert(std::is_same_v<decltype(f(0)), int&&>);  // C++20: int&
static_assert(std::is_same_v<decltype(g(0)), int&&>);  // C++20: int&
int main() {}
```

`g` returns an rvalue reference bound to its parameter, which dangles after the function returns; in C++20 it returns `int&`, which dangles just the same. Clang 23 gives a `-Wreturn-stack-address` warning for `g` in both modes. P2266's view is that parentheses near `decltype(auto)` were already something to be wary of, and this adds few new surprises. Other forms of dangling references are covered in [[topics/dangling-references]].

The `std::reference_wrapper` and `Quest` examples both become ill-formed in C++23. P2266 regards the former as an improvement: the compiler finally diagnoses the dangling reference.

### How much code actually broke

P2266R1 was implemented as the default behavior in Clang 13's `-std=c++2b` mode in 2021. The paper reports three breakages found in industry code during that period, all considered questionable code and since changed:

| Original code | Problem | Change |
|---|---|---|
| `istream& getline(istream&& in, …) { …; return in; }` | Rvalue reference parameter returned as an lvalue reference | `return static_cast<istream&>(in);` |
| `template<class T> T& temporary(T&& x) { return x; }` | Same as above | `return static_cast<T&>(x);` |
| `X f() { char a[10]; return a; }`, `X(auto&)` | `a` becomes `char(&&)[10]`, which can't bind to `auto&` | `return X(a);` |

The third is subtler: the return type is a class, but its constructor is a template that only accepts lvalues. Clang 23 accepts it under `-std=c++20` and reports no viable conversion under `-std=c++23`.

Because it breaks well-formed old code, the committee did not treat P2266 as a defect report; it belongs to C++23 only. The feature-test macro is `__cpp_implicit_move`; Clang 23 defines it as `202207L` under `-std=c++23` and does not define it under `-std=c++20`.

## Wording changes

In C++20, implicit move was paragraph 3 of [class.copy.elision], describing two-stage resolution. P2266 considered the copy elision section no longer the right place for implicit move, moved it wholesale into the value category rules for name expressions, and deleted the original paragraph. Today's [[class.copy.elision#3]] has only an example left, showing the results for `Weird`, `int& h(bool, int)` and `decltype(auto)` under the new rules.

The new rule is in two places. [[expr.prim.id.unqual#12]] changes how the value category is determined, checking move-eligibility first:

!!! std
    The expression is an xvalue if it is move-eligible (see below); an lvalue if the entity is a function, variable, structured binding, ...
    
    A name expression that is move-eligible is an xvalue; otherwise whether it is an lvalue or a prvalue depends on the kind of entity.

[[expr.prim.id.unqual#15]] defines implicitly movable entity and move-eligible:

- ¶15.1 the expression denotes an implicitly movable entity;
- ¶15.2 it is the (possibly parenthesized) operand of a `return` or `co_return` statement or of a *throw-expression*;
- ¶15.3 every scope intervening between the entity's declaration and the innermost scope containing the expression is a block scope; for `throw`, these scopes also must not be the block scope of a `try` block or function `try` block.

¶15.3 is phrased differently from P2266's original text. P2266 spoke of the entity being declared in the body or parameter list of the innermost enclosing function or lambda; the current draft phrases it in terms of scopes instead, with the same meaning: a `return` in a lambda body of a local variable of the enclosing function has the lambda's scope in between, so it is not move-eligible. ¶15 also mentions *splice-expression*, which was added by C++26 static reflection.

The other changes are all non-normative: a note in [[basic.lval#4]] lists move-eligible names as the first kind of xvalue; the example in [[dcl.type.auto.deduct#4]] gains `auto f2(int x) -> decltype(auto) { return (x); }` deducing `int&&`; [[diff.cpp20.expr#1]] records the incompatibility. Note 2 in [[stmt.return#2]] still says that when an automatic variable is returned, the copy may be elided or converted to a move, with the details in [[class.copy.elision]].

## How to write it today

**When returning local variables and parameters, just write the name.** `return std::move(local);` turns the expression into a function call; it is no longer a name, so it loses eligibility for NRVO. In Clang's `-Wall`, `-Wpessimizing-move` reports a `std::move` that prevents copy elision, and `-Wredundant-move` reports a redundant `std::move` on a by-value parameter. Clang 23 does not report `std::string a(std::string&& s) { return std::move(s); }` as redundant in any mode, even though that `std::move` has been unnecessary since C++20.

**When an rvalue reference parameter is to be returned as an lvalue reference, write the conversion.** For example `return static_cast<T&>(x);`. That is exactly how the three pieces of industry code above were fixed.

**The following names are not move-eligible, and still copy:**

```cpp title="not-eligible.cpp" run ok
#include <cstdio>
struct W {
  W() {}
  W(const W&) { std::puts("copy"); }
  W(W&&) { std::puts("move"); }
};
struct P { W a, b; };

W sb()   { auto [a, b] = P{}; return a; }        // a structured binding is not a variable
W lam()  { W w; return [&] { return w; }(); }    // w belongs to the enclosing function
W memb() { P p; return p.a; }                    // member access is not a name

int main() { sb(); lam(); memb(); }
```

Clang 23 prints three lines of `copy` under `-std=c++20`, `-std=c++23` and `-std=c++2c`. To move, write `std::move`. Conditional expressions, `*p` and `std::get<0>(t)` are the same; what each of them costs is covered in [[perf/copies-and-moves]].

When each special member is called and how implicit move interacts with NRVO is covered in [[topics/special-members-and-elision]]; the full evolution from C++11 to C++26 is in [[history/move-semantics]].

## Compiler support

The table below was measured with Clang 23.1.3; `-fsyntax-only` decides whether it compiles, and examples with a `main` were also run.

| Example | `-std=c++11` | `-std=c++17` | `-std=c++20` | `-std=c++23` |
|---|---|---|---|---|
| `unique_ptr<D>` returned as `unique_ptr<B>` | Move | Move | Move | Move |
| `return d;` slicing to a base, by-value parameters, conversion functions | Move | Move | Move | Move |
| `W f(W&& r) { return r; }`, `throw` of a parameter | Move | Move | Move | Move |
| `W&& f(W&& w) { return w; }` | Error | Error | Error | Passes |
| `int& g(int&& x) { return x; }` | Passes | Passes | Passes | Error |
| `Weird(Weird&)`, `Quest`, `reference_wrapper`, `X(auto&)` | Passes | Passes | Passes | Error |
| `Frodo(W&&) = delete` | Error | Error | Error | Error |

The first three rows show that Clang treats CWG1579 and P1825 as defect reports; the later rows show that P2266 takes effect only from C++23 on. `Frodo` is an error in every mode, consistent with a strict reading of [[over.match.general#3]]. GCC and MSVC were not tested.

## Questions

!!! question "1. Parentheses in a trailing return type"
    What type does the function below return in C++20 and in C++23, and is it well-formed?
    
    ```cpp
    auto f(int x) -> decltype((x)) { return (x); }
    ```

<details markdown="1">
<summary>Answer</summary>

The trailing return type is not in a `return` statement, so the `x` in `decltype((x))` is an ordinary lvalue and the return type is `int&` in both versions. The `(x)` in the function body is a move-eligible xvalue in C++23 ([[expr.prim.id.unqual#15]]), which cannot bind to `int&`, so it is ill-formed in C++23; in C++20 it is well-formed but returns a dangling reference to the parameter. Clang 23 gives a `-Wreturn-stack-address` warning under `-std=c++20` and an error under `-std=c++23`.

</details>

!!! question "2. Why `throw x;` has a scope condition"
    ```cpp
    void g(const W&);
    void f() {
      W x;
      try { g(x); throw x; }
      catch (...) { g(x); }
    }
    ```
    Does this `throw x;` move `x`?

<details markdown="1">
<summary>Answer</summary>

No. The block scope of the `try` block lies between the declaration of `x` and the `throw`, so ¶15.3 is not satisfied, `x` is not move-eligible, and the exception object is copy-initialized (Clang 23 prints `copy` at run time). The reason is that the exception may be caught by a `catch` in the same function, which then uses `x` again; if it had been moved from, the `catch` would see a hollowed-out object. The example in [[class.copy.elision#4]] shows the same situation.

</details>
