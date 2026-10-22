---
title: How move semantics and value categories came about
summary: Why rvalue references can't bind to lvalues, why a class with a destructor gets no implicit move operations, where names like xvalue come from, why C++17 changed what a prvalue means, and why the rules for when return x; moves changed four times; from the copying problem of C++98 to C++26.
tags: move semantics, rvalue references, value categories, copy elision, implicit move, trivial relocation
updated: 2026-10-19
---

!!! tldr
    - C++98 could tell lvalues from rvalues, but a function had no way to know that its argument was a temporary about to be destroyed, so it could only copy. Rvalue references `T&&` were added for exactly this.
    - Rvalue references could at first bind to lvalues, and when an overload was removed they silently moved from lvalues; this was changed to today's rule in 2009. Move operations are not implicitly generated for a class with a user-declared destructor, also so as not to break old code.
    - glvalue, xvalue and prvalue are names coined in 2010 to make the standard's wording consistent. C++17 then redefined a prvalue as a way of initializing an object, which guarantees that `T x = T();` does not copy.
    - When `return x;` moves automatically changed once each in C++11, C++14, C++20 and C++23; two of those were retroactive defect reports, so compilers in older language modes don't necessarily behave as the standard of that year said.
    - C++26 forbids returning a reference bound to a temporary. Trivial relocation went into C++26 for a while, was taken out again, and is left for C++29.

The rules themselves are in [[basic.lval]], [[class.temporary]], [[class.copy.elision]], [[dcl.init.ref]] and [[stmt.return]]; for working out an expression's value category see [[topics/value-categories]], and for when special member functions are implicitly generated see [[topics/special-members-and-elision]].

All examples on this page have been checked with Clang 23 under different `-std=` settings. Examples whose behavior changes between versions have no verdict marker; the verdict is in a comment at the end of the line.

## C++98: lvalues and rvalues distinguished, but resources can't be taken

In C++98 every expression is either an **lvalue** (referring to an object with identity, whose address can be taken) or an **rvalue** (such as literals and temporaries returned by functions). This dichotomy comes from C and mainly answers two questions: can its address be taken or can it appear on the left of a built-in assignment, and can it bind to a non-const lvalue reference `T&`.

The second rule is where the whole later story begins. C++98 says an rvalue cannot bind to `T&`, only to `const T&` ([[dcl.init.ref]]). This protects programmers: passing a temporary to a function that intends to modify its argument is almost always a mistake. The cost is that a function cannot tell a temporary about to be destroyed from a const object the caller will use again later. Both can only be received as `const T&`, and once it has them, the function can only copy, not take the resources.

## Copy elision: only a permission

The cost of returning large objects was first addressed by optimization. Before standardization, someone proposed a language extension to name the return object in the function header, arguing that without it compilers could not reliably eliminate the copy. Zortech C++ and Cfront then implemented the named return value optimization (NRVO) without any extension, which was taken as proof that the extension was unnecessary (Lippman, *The Name Return Value Optimization*, 2004).

C++98 wrote this practice down as a permission, not an obligation: when returning a local object from a function, or initializing an object from a temporary of the same type, an implementation may omit the copy construction, even if it has side effects. Because it was only a permission, the standard still required the omitted copy constructor to be accessible. The type below could not be returned by value before C++14, even though no mainstream compiler would actually call that copy constructor:

```cpp run title="private-copy.cpp" std=c++14
struct NoMove {
    NoMove() {}
private:
    NoMove(const NoMove&);   // C++98-style copy prohibition
};

NoMove make() { return NoMove(); }   // C++14 and earlier: error, copy constructor inaccessible
                                     // since C++17: OK, see below
int main() {
    NoMove x = make();               // same as above
    (void)x;
}
```

Another problem with a permission is that programmers cannot tell from the source whether the optimization happens. Turning off optional elision with Clang's `-fno-elide-constructors` shows the two copies that theoretically exist under C++98 semantics:

```cpp run title="elision-count.cpp" flags="-std=c++14 -fno-elide-constructors"
#include <cstdio>
struct S {
    S()         { std::puts("ctor"); }
    S(const S&) { std::puts("copy"); }
    ~S()        { std::puts("dtor"); }
};
S make() { return S(); }
int main() { S s = make(); }
// -std=c++98/c++14 -fno-elide-constructors: ctor copy dtor copy dtor dtor
// -std=c++17       -fno-elide-constructors: ctor dtor
```

## Workarounds before C++11

Copy elision only covers returning and initializing from a temporary. Putting things into a container, growing a container and handing over ownership could only copy in C++98. Stroustrup considers this one of the main sources of heavy explicit pointer use: to hand a large chunk of data out of a function, people allocated it on the free store and passed a pointer around (HOPL IV §4.2.3). Library authors came up with several workarounds, each of which exposed something the language lacked.

**The swap trick.** A container's member `swap` only exchanges a few internal pointers, so constructing locally and then swapping into the target became an idiom:

```cpp run title="swap98.cpp" std=c++98 ok
#include <vector>
#include <string>
std::vector<std::string> v;

void refill() {
    std::vector<std::string> tmp(1000, std::string(100, 'x'));
    v.swap(tmp);                              // swaps three pointers, copies no elements
}
void shrink() {
    std::vector<std::string>(v).swap(v);      // the C++98 way to shrink capacity
}
int main() { refill(); shrink(); return v.size() == 1000 ? 0 : 1; }
```

It only works for operations that can be expressed as a swap; when the container grows by itself, it still copies elements one by one.

**auto_ptr.** `std::auto_ptr` implemented ownership transfer with copy syntax: its copy constructor took a non-const reference and nulled out the source.

```cpp run title="auto-ptr.cpp" std=c++98 ok
#include <memory>
#include <cassert>
int main() {
    std::auto_ptr<int> p(new int(1));
    std::auto_ptr<int> q = p;     // looks like a copy, actually transfers ownership
    assert(p.get() == 0);         // p has been nulled
    assert(*q == 1);
}
```

Copy syntax without copy semantics meant `auto_ptr` could not safely be put in containers or handed to generic algorithms that assume two objects are equal after a copy. To be constructible from a temporary returned by a function, it also needed the helper class `auto_ptr_ref`. C++11 deprecated it in favor of [[unique.ptr]]; C++17 removed it ([[N4190]]). Clang 23 with libc++ gives a deprecation warning under `-std=c++11`, and under `-std=c++17` reports `no member named 'auto_ptr' in namespace 'std'`.

**Mojo.** Andrei Alexandrescu's pure-library solution from 2003 used a set of wrapper types and overload resolution to single out, at library level, arguments whose resources could be taken (Alexandrescu, *Move Constructors*, CUJ 2003). It showed that the distinction was feasible, and also what it cost: every type had to be rewritten, and the number of overloads doubled.

## The design of rvalue references (2002)

[[N1377]] (Hinnant, Dimov, Abrahams) proposed a new kind of reference, `A&&`, called an **rvalue reference**. Several of its core design points survive to this day:

- `A&&` is a different type from `A&` and can be overloaded on, so a move constructor `A(A&&)` and a copy constructor `A(const A&)` can coexist;
- A named rvalue reference is treated as an lvalue, an unnamed one as an rvalue. That way, an object used once in a function body is not accidentally moved from the next time it is used;
- Moving from an lvalue requires an explicit cast, such as `static_cast<A&&>(x)`, which later became `std::move`;
- When the parameter is `T&&`, an lvalue argument deduces `T` as an lvalue reference type. This is the basis of perfect forwarding.

The last point solves the forwarding problem raised at the same time by [[N1385]]: writing a wrapper function that passes its arguments unchanged to another function. The two C++98 approaches each had a flaw, and forwarding n parameters correctly needed 2ⁿ overloads:

<div class="compare" markdown="1">

```cpp title="C++98" error
void g(int&);
void g(const int&);

template <class T>
void wrap1(T& a) { g(a); }
template <class T>
void wrap2(const T& a) { g(a); }

void test() {
  int i = 0;
  wrap1(42); // error: an rvalue can't bind to T&
  wrap2(i);  // picks g(const int&)
}
```

```cpp title="C++11" ok
#include <utility>
void g(int&);
void g(const int&);
void g(int&&);

template <class T>
void wrap(T&& a) {
  g(std::forward<T>(a));
}
// wrap(i)  → g(int&)
// wrap(ci) → g(const int&)
// wrap(42) → g(int&&)
```

</div>

The standard did not introduce a separate type for `T&&` in a deduced context. [[N4164]] suggested calling such parameters **forwarding references**, and the standard has used that term since C++17 ([[temp.deduct.call]]).

## Detour one: rvalue references could once bind to lvalues (fixed in 2009)

Under N1377 and the version that entered the draft in 2006, lvalues could bind to rvalue references; overload resolution simply preferred an `A&` overload when there was one. As long as both overloads existed, this was fine.

[[N2812]] pointed out that once one of the overloads is removed, the rule becomes unsafe. Its example was `std::list<std::unique_ptr<int>>`: the elements are not copyable, so `push_back(const value_type&)` is removed by constraints or SFINAE, but the remaining `push_back(value_type&&)` accepts lvalues, so `l.push_back(a)` silently moves from the lvalue `a`. The paper's summary was that the copy/move overload set "doesn't degrade safely".

The fix was to forbid rvalue references from binding to lvalues. That way, when one of the copy/move overloads is removed, an lvalue argument gets a compile error instead of being silently moved from:

```cpp run title="rvalue-ref-binding.cpp" error
int main() {
    int i = 0;
    int&& r = i;     // error: an rvalue reference can't bind to an lvalue
    (void)r;
}
```

This change left a mark on `std::forward`: it had to be redesigned, because the old implementation relied on lvalues binding to rvalue references.

## Detour two: moves that throw (where noexcept came from)

In C++98 `std::vector::push_back` provides the strong exception safety guarantee: if copying elements fails while growing, the original elements are intact. With moves instead, if a move constructor throws partway through, the elements already moved cannot be recovered ([[N2855]]).

The final solution ([[N3050]]) allowed move constructors to throw, and at the same time added the `noexcept` specifier and `std::move_if_noexcept`: where the standard library needs the strong guarantee, it moves only when moving cannot throw (or the type is not copyable). That is why `std::vector` today only uses moves when growing if the move constructor is `noexcept`; details are in [[topics/special-members-and-elision]].

## Detour three: implicitly generated move operations (where the Rule of Five came from)

When rvalue references entered the draft, compilers did not implicitly generate move operations for classes. [[N3053]] in 2010 added implicit generation: a move constructor was implicitly declared as long as the class had no user-declared copy constructor and the implicit move constructor would not be defined as deleted. A user-declared destructor was not among the suppressing conditions.

[[N3153]] (*Implicit Move Must Go*) immediately pointed out that this would silently change correct old programs. Its example was a class maintaining an invariant: a member `vector` always has 5 elements, and the destructor reads `v[0]`. Under N3053, `y.push_back(X())` would implicitly move from the temporary, emptying its `vector`, and the destructor would then read out of bounds. The paper recorded that g++ 4.6's C++0x mode at the time really did make this C++03 program fail.

The committee had two choices: remove implicit moves ([[N3216]]), or tighten the conditions ([[N3203]]). Removing them would leave simple types such as aggregates unable to move, and users would have to write a set of `= default`s for every class; keeping them required guaranteeing that old classes with invariants were unaffected. What passed was tightening: if a class has a user-declared copy constructor, copy assignment, move operation or destructor, no move operations are implicitly declared. At the same time, implicitly generating copy operations when there is a user-declared destructor or another copy operation was marked deprecated.

That is the rule behind the Rule of Five, and it explains the output of this program:

```cpp run title="implicit-move.cpp" std=c++11 ok
#include <cstdio>
#include <utility>
struct Tracer {
    Tracer() {}
    Tracer(const Tracer&) { std::puts("copy"); }
    Tracer(Tracer&&)      { std::puts("move"); }
};
struct Plain    { Tracer t; };                 // move constructor implicitly declared
struct WithDtor { Tracer t; ~WithDtor() {} };  // user-declared destructor: no move
int main() {
    Plain a;    Plain b = std::move(a);        // prints move
    WithDtor c; WithDtor d = std::move(c);     // prints copy: falls back to the copy constructor
}
```

Compiled with `-Wdeprecated`, Clang 23 gives a `-Wdeprecated-copy-with-user-provided-dtor` warning for the second class, corresponding exactly to the deprecation N3203 introduced. That deprecation has still not become a removal; see [[depr.impldec]].

## Naming the five value categories (2010)

Rvalue references created a problem for the standard's wording: what do you call an expression like `static_cast<T&&>(x)`, or a call to a function returning `T&&`? It refers to a definite object, like an lvalue; yet it can bind to an rvalue reference and be moved from, like an rvalue. By then the core language and library parts of the standard were already using the word rvalue inconsistently.

Stroustrup's analysis was that there are only two independent properties (Stroustrup, *"New" Value Terminology*; HOPL IV §4.2.3):

- **Has identity**: has an address, and you can tell whether two expressions refer to the same object;
- **Can be moved from**: the source may be left in a valid but unspecified state.

The combination of no identity and not movable is of no use in C++, leaving three basic categories, plus two broader categories grouped by each of the two properties. The naming constraints were to keep "every expression is either an lvalue or an rvalue", and to stay consistent with the library wording where rvalue means "can be moved from":

| Properties | Name | Origin |
|---|---|---|
| Has identity, cannot be moved from | lvalue | Keeps the traditional meaning |
| Has identity | glvalue | generalized lvalue |
| Has identity, can be moved from | xvalue | The standard's note explains it as eXpiring ([[basic.lval#3]]) |
| No identity, can be moved from | prvalue | pure rvalue |
| Can be moved from | rvalue | Consistent with the library wording |

[[N3055]] rewrote the wording accordingly. It did not change what counts as an lvalue or an rvalue; it only gave a name to the part of rvalues that has identity. Value categories are still properties of expressions, not of values or objects (the note in [[basic.lval#3]] makes a point of this).

## The return rules of C++11 and C++14

C++11 made `return local;` move even without `std::move`, so that move-only types like `std::unique_ptr` could be returned by value. The rule was a two-stage overload resolution: if the operand is a local object eligible for copy elision, first do overload resolution treating it as an rvalue; if the first parameter of the selected constructor is not an rvalue reference to the object's type, redo it treating the object as an lvalue.

During C++14 there were two defect fixes, both relaxing this mechanism:

- [[CWG1579]]: the original rule required the operand to have the same type as the return type, so `optional<T> f() { T t; return t; }` could only copy. After the fix, as long as the other conditions are met, the rvalue attempt comes first.
- [[CWG1402]]: under the original rule, an explicitly defaulted (`= default`) move constructor was easily defined as deleted, and deleted functions take part in overload resolution, so returning by value would select it and fail. After the fix, a defaulted move operation defined as deleted does not take part in overload resolution, and resolution falls back to copying.

## C++17: guaranteed copy elision

As of C++14, copy elision when returning a temporary was still only a permission, and the `NoMove` above still could not be returned by value. [[P0135R1]] did not simply turn the permission into an obligation; it changed what a prvalue means.

In C++14, `T()` is a temporary object, and `T x = T();` in theory copies or moves from that temporary into `x`. Since C++17, a prvalue is not itself an object but a way of initializing an object. The object it initializes is called its **result object**. Only when a prvalue appears where a glvalue is needed, such as when binding a reference or accessing a member, is a temporary object created through **temporary materialization** ([[basic.lval#5]], [[class.temporary]]).

<div class="compare" markdown="1">

```cpp title="The C++14 view"
T x = T();
// 1. T() creates a temporary
// 2. copy/move from it into x (may be elided)
// 3. the copy/move constructor must be usable
```

```cpp title="The C++17 view"
T x = T();
// T() is a prvalue that initializes x directly
// there's no intermediate temporary,
// and no copy/move constructor is needed
```

</div>

The same holds for returning a prvalue: the return statement directly initializes the caller's result object. So `NoMove` can be returned by value in C++17, and `-fno-elide-constructors` cannot insert a copy any more. Likewise, `std::atomic<int> a = std::atomic<int>(0);` is ill-formed in C++14 (Clang reports a call to the implicitly deleted copy constructor) and valid in C++17.

Only the prvalue case is guaranteed. In `T f() { T x; return x; }`, eliding the copy from `x` into the result object, that is NRVO, is still only a permission ([[class.copy.elision#1.1]]). [[P2025R2]], a proposal to guarantee NRVO, has not entered the working draft.

## Implicit move relaxed twice more (C++20, C++23)

### C++20: more cases can move (P1825)

The C++11/14 rules still had gaps: `return r;` did not move when the local variable was an rvalue reference; parameters did not move in a `throw`; and the first parameter had to be an rvalue reference to the object's type, so in `Base f() { Derived d; return d; }` the first attempt picked `Base(Base&&)`, then fell back to copying because that isn't `Derived&&`. [[P1825R0]] filled these gaps, introduced the term implicitly movable entity, and was accepted as a defect report.

```cpp run title="more-implicit-moves.cpp" std=c++20 ok
#include <cstdio>
struct Base {
    Base() {}
    Base(const Base&) { std::puts("copy"); }
    Base(Base&&)      { std::puts("move"); }
};
struct Derived : Base {};

Base f() { Derived d; return d; }   // wording before P1825: copy; after: move
Base g(Base&& r) { return r; }      // wording before P1825: copy; after: move

int main() { f(); Base b; g(static_cast<Base&&>(b)); }
```

Because it is a defect report, implementations apply it to older language modes: Clang 23 prints two lines of move under every mode from `-std=c++11` to `-std=c++20`. With today's compilers you can no longer see the behavior of the original C++17 wording.

### C++23: one rule replaces two stages (P2266)

The two-stage overload resolution rule was complicated, and it only applied to choosing a constructor, not to functions returning references. [[P2266R3]] replaced it with a single rule: in return, co_return and throw, an id-expression that names an implicitly movable entity is itself an xvalue, called **move-eligible** ([[expr.prim.id.unqual#15]]). There is no second attempt.

From then on, the same name `w` is an xvalue in a return statement and an lvalue elsewhere. This change is not a defect report, and Clang only applies it in C++23 and later, so you can compare directly:

```cpp run title="simpler-implicit-move.cpp" std=c++23
#include <type_traits>

struct Widget { Widget(); Widget(Widget&&); };
Widget&& pass(Widget&& w) {
    return w;          // C++20: error, w is an lvalue; C++23: OK, w is an xvalue
}

int& bad(int&& x) {
    return x;          // C++20: OK; C++23: error, an xvalue can't bind to int&
}

decltype(auto) h(int&& x) { return (x); }
static_assert(std::is_same_v<decltype(h(0)), int&&>);   // holds in C++23; int& in C++20

int main() {}
```

`bad` being valid in C++20 and ill-formed in C++23 is an incompatibility P2266 explicitly accepted. The `decltype(auto)` change has the same cause: `decltype` applied to a parenthesized expression reflects its value category, and that value category changed inside return statements.

## C++26: returning a reference bound to a temporary is forbidden

Returning a reference bound to a temporary has always produced a dangling reference, but the program used to be well-formed and compilers could only warn. [[P2748R5]] made it ill-formed:

```cpp run title="return-temporary.cpp" std=c++2c
const int& f() {
    return 42;         // C++23 and earlier: well-formed, Clang warns
}                      // C++26: error, the returned reference binds to a temporary
struct S { };
const S& g() { return S(); }   // same as above
int main() {}
```

Clang 23 gives a `returning reference to local temporary object` warning for both under `-std=c++23`, and makes the same diagnostic an error under `-std=c++2c`. [[stmt.return#6]] in the current draft goes further: if a constituent reference of the returned object (for example a reference member of an aggregate) binds to a temporary, that is ill-formed too. This is new wording after C++23, and this page has not verified which proposal it comes from. Other forms of dangling references are covered in [[topics/dangling-references]].

## Trivial relocation: into C++26 and out again

For many types, a move followed by a destruction (moving an object to a new location and then destroying the original) can be done with a single `memcpy`; in common implementations `std::unique_ptr` and `std::vector` are examples. A container that knows this can copy memory in bulk when growing. Libraries such as Abseil, Folly and Qt already do this ([[P1144R13]]), but under the standard's object model, moving a non-trivially-copyable object with `memcpy` is undefined behavior.

There were two competing approaches to standardizing it: [[P1144R13]] (*std::is_trivially_relocatable*) and [[P2786R13]] (*Trivial Relocatability For C++26*). They made different trade-offs on how a type is declared trivially relocatable and on whether swap and assignment can be optimized the same way. In February 2025 C++26 adopted P2786R13.

In November of the same year, while handling national body comments, the committee removed it from C++26 by consensus, including the contextual keywords such as `trivially_relocatable_if_eligible`, type traits such as `is_trivially_relocatable`, and `std::trivially_relocate` ([[P3920R0]]). Sutter's trip report says the committee found a problem that could not be fixed within the C++26 schedule (Sutter, Kona trip report, 2025-11). [[P4197R0]] then laid out the design questions C++29 needs to answer, such as whether relocation should be a byte copy or a dedicated abstract-machine operation, and whether relocation that needs to fix up pointers should be allowed. So as of this writing, C++26 has no trivial relocation.

## Looking back

This history has kept answering the same question: when can we avoid copying? C++98 allowed implementations not to copy; C++11 let programmers ask for a move explicitly, and moved automatically when returning local variables; C++17 made copies not exist at all in some cases. The traces left by each step are things you run into when reading the standard today:

- Value category is a property of expressions, and since C++23 it also depends on context (move-eligible id-expressions in return, co_return and throw).
- Since C++17, a prvalue is not a temporary object. To ask "is there a temporary here", look at whether the prvalue is materialized, not at whether it is an rvalue.
- Only copy elision of prvalues is guaranteed. NRVO is still a permission, and the elided copy or move constructor must still be usable ([[class.copy.elision]]).
- The implicit move rules changed four times, and two of those were defect reports. When checking differences between versions, distinguish the standard's original wording from what compilers actually do in old modes.

## Timeline

| Year | Event | Reference |
|---|---|---|
| 1998 | lvalue/rvalue dichotomy; copy elision only a permission; `auto_ptr` | C++98 |
| 2002 | Rvalue reference and move semantics proposal; the forwarding problem | [[N1377]], [[N1385]] |
| 2009 | Rvalue references no longer bind to lvalues | [[N2812]] |
| 2010 | `noexcept` and `move_if_noexcept`; the five value categories; implicit moves tightened | [[N3050]], [[N3055]], [[N3203]] |
| 2011 | C++11 published | |
| 2013–2014 | Moving via converting constructors on return; deleted defaulted moves excluded from overload resolution (DR) | [[CWG1579]], [[CWG1402]] |
| 2016 | Guaranteed copy elision, prvalue redefined (C++17) | [[P0135R1]] |
| 2019 | More implicit moves (DR) | [[P1825R0]] |
| 2022 | Simpler implicit move (C++23) | [[P2266R3]] |
| 2024 | Returning a reference bound to a temporary forbidden (C++26) | [[P2748R5]] |
| 2025 | Trivial relocation goes into and out of C++26 | [[P2786R13]], [[P3920R0]] |

## References

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV (2020), §4.2.3 *Move Semantics*.
- Bjarne Stroustrup. *"New" Value Terminology*, 2010, stroustrup.com/terminology.pdf.
- Stanley B. Lippman. *The Name Return Value Optimization*, MSDN blog, 2004.
- Andrei Alexandrescu. *Generic&lt;Programming&gt;: Move Constructors*, C/C++ Users Journal, 2003-02.
- [[N1377]] *A Proposal to Add Move Semantics Support to the C++ Language*; [[N1385]] *The Forwarding Problem: Arguments*.
- [[N2812]] *A Safety Problem with RValue References (and what to do about it)*.
- [[N2855]] *Rvalue References and Exception Safety*; [[N3050]] *Allowing Move Constructors to Throw*.
- [[N3053]] *Defining Move Special Member Functions*; [[N3153]] *Implicit Move Must Go*; [[N3203]] *Tightening the conditions for generating implicit moves*; [[N3216]] *Removing Implicit Move Constructors and Move Assignment Operators*.
- [[N3055]] *A Taxonomy of Expression Value Categories*.
- [[P0135R1]] *Wording for guaranteed copy elision through simplified value categories*.
- [[P1825R0]] *Merged wording for P0527R1 and P1155R3*; [[P2266R3]] *Simpler implicit move*; [[P2748R5]] *Disallow Binding a Returned Glvalue to a Temporary*.
- [[P1144R13]], [[P2786R13]], [[P3920R0]], [[P4197R0]]: trivial relocation; Herb Sutter, *Trip report: November 2025 ISO C++ standards meeting (Kona, USA)*.
