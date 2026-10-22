---
title: Guaranteed copy elision (P0135)
summary: How C++17 lets types that can be neither copied nor moved be returned by value from factory functions. P0135 did not change copy elision from permitted to required; it redefined prvalues so that, until materialized, a prvalue is not an object at all.
tags: proposal, copy elision, value categories, prvalue, temporary materialization, C++17
group: Core language
updated: 2026-10-19
---

!!! tldr
    - C++14 allowed compilers to elide the copy from a temporary into the target object, but the elided constructor still had to be usable, so types like `std::atomic` and `std::lock_guard` could not have factory functions returning by value.
    - P0135 did not make that elision mandatory; it redefined prvalues instead: a prvalue is an initialization, not an object, and a temporary object is created through temporary materialization only when a glvalue is needed.
    - So when an object is initialized from a prvalue of the same type, there is semantically no copy or move to elide, and no copy or move constructor is needed.
    - The guarantee only covers prvalues. NRVO for `return local;` is still merely permitted, and corner cases such as base class subobjects and direct initialization via conversion functions still have open CWG issues.
    - For trivially copyable types, implementations are still allowed one extra copy (to pass the object in registers), and in that case the object's address changes.

## C++14: factory functions that couldn't be written

```cpp run title="factory.cpp" ok
#include <atomic>
#include <mutex>

std::atomic<int> make_counter() {
  return std::atomic<int>(0);           // C++14: needs the deleted copy constructor
}

struct Pinned {
  explicit Pinned(int v) : v(v) {}
  Pinned(const Pinned&) = delete;
  Pinned(Pinned&&) = delete;
  int v;
};
Pinned make_pinned(int v) { return Pinned(v); }

int main() {
  auto c = make_counter();
  auto p = make_pinned(42);
  std::mutex m;
  auto g = std::lock_guard<std::mutex>(m);   // the auto x = T(...) style
  return p.v - 42 + c.load();
}
```

Clang 23 compiles this with `-std=c++17`; with `-std=c++14` it reports errors in five places: the two `return`s and the three `auto` declarations, each diagnosed as a call to a deleted (or implicitly deleted) constructor.

The C++14 model is this: `Pinned(v)` creates a temporary object, `return` copies or moves the return value out of it, and the caller copies or moves from the return value into `p`. The standard allowed implementations to elide these copies (C++14 [class.copy] ¶31), and in practice compilers always did, but before eliding they had to confirm the copy was semantically possible: the selected constructor had to be accessible and not deleted. Both the programmer and the compiler knew this constructor would never be called, and the code still didn't compile.

At the time, the only option was a workaround:

<div class="compare" markdown="1">

```cpp
// put it on the heap
std::unique_ptr<Pinned>
make_pinned(int v) {
  return std::make_unique<Pinned>(v);
}
```

```cpp
// two-phase initialization
void init_pinned(Pinned& out, int v);

Pinned p(0);        // construct first
init_pinned(p, 42); // then fill in
```

</div>

The former costs an extra dynamic allocation and a level of indirection; the latter requires the type to have an empty state. [[P0135R0]] also mentions a style problem: people used to writing `auto x = make();` have to fall back to some other form when the type is not movable. Even when the type is movable, portable code cannot rely on the elision happening, so for very large objects some people still preferred output parameters.

## The design space

### Three paths

Richard Smith, the author of P0135R0, lists three options in the paper:

1. **Do nothing.** The cost is the problems from the previous section: no performance guarantee, constructors that are never called must still be provided, and factory functions for non-movable types can't be written.
2. **Guarantee copy elision some other way**, keeping the model in which `T(...)` creates a temporary object and only requiring that this copy be elided. The paper considers it unclear how to write such a rule, and says it would miss an opportunity to make value categories easier to learn.
3. **Rewrite the definition of value categories** so that this copy never exists in the first place. This is the final approach.

The difficulty with the second path can be understood like this: if you still say that `T x = T();` has a temporary object and a copy, then requiring that the copy be elided without checking the constructor amounts to saying the program contains a copy that is never allowed to happen, which makes the model contradict itself. The paper points out that the model of `T(...)` creating a temporary object only ever held for class types anyway: `int()` has never been an object; it is just a value.

### Only prvalues, not NRVO

C++14 allowed copies to be elided in three kinds of situation: initializing another object from a temporary (including return values and exception objects), `return` or `throw` of a variable about to go out of scope, and `catch` by value. P0135 only deals with the first kind.

The paper acknowledges that reliable NRVO (named return value optimization, eliding the copy when returning a named local variable) matters for reasoning about performance, but whether it can happen depends on the shape of all the `return`s in the function, which makes a simple guarantee hard to give. So the elision in `T f() { T t; return t; }` is still permitted rather than guaranteed to this day; see below.

### Defining prvalues from a different angle

The core of the approach is one sentence: prvalues perform initialization, glvalues produce locations.

```cpp
struct X { int n; };
extern X x;
X{4};      // prvalue: means "initialize an X"
x.n;       // glvalue: the location of member n of x
X{4}.n;    // glvalue (xvalue): the location of member n of X{4}
```

The paper stresses that this rewording by itself does not change the classification of any expression: `X{4}` is still a prvalue and `X{4}.n` is still an xvalue. The change comes afterwards: if a prvalue is only an initialization, there is no reason for `T()` to create a temporary object on its own. Whether a temporary object is needed should be decided by the context in which the prvalue appears, and a context that uses it to initialize an object of the same type does not need one at all.

Copy-initialization like `T x = 5;` changed as a result:

```cpp run title="convert.cpp" ok
struct Pinned {
  Pinned(int v) : v(v) {}               // converting constructor
  Pinned(const Pinned&) = delete;
  int v;
};
Pinned x = 5;   // C++14: construct a temporary, then copy (deleted); C++17: construct x directly
int main() { return x.v - 5; }
```

Clang 23 reports "copying variable of type 'Pinned' invokes deleted constructor" under `-std=c++14` and accepts it under `-std=c++17`.

## The final wording

[[P0135R1]] provided the wording, resolving four issues at once, [[CWG1565]], [[CWG1590]], [[CWG1599]] and [[CWG1697]], and partially resolving [[CWG2022]] (copy elision in constant expressions, except NRVO). The key changes are listed below by their location in the current draft.

### Prvalues and result objects

The definitions of the value categories were changed to classify by what evaluation does ([[basic.lval#1]]):

!!! std
    A *prvalue* is an expression whose evaluation initializes an object or computes the value of an operand of an operator, as specified by the context in which it appears, or an expression that has type cv void.

A prvalue initializes an object or computes the value of an operand of an operator; which one is decided by the context it appears in. The object it initializes is called its **result object** ([[g:result-object|result object]], [[basic.lval#5]]). In `T x = make();`, the result object of `make()` is `x`; the `return Pinned(v);` in `make` in turn initializes the result object of the call with the prvalue `Pinned(v)`, so the result object of `Pinned(v)` is also `x`. Passed down level by level, the constructor ends up running directly on the storage of `x`.

### Temporary materialization

When a prvalue appears where a glvalue is needed, such as binding a reference or accessing a member, there really has to be an object. The new **temporary materialization conversion** ([[g:temporary-materialization-conversion|temporary materialization conversion]], [[conv.rval#1]]) takes care of this: it creates a temporary object, evaluates the prvalue with that object as its result object, and yields an xvalue denoting it.

[[basic.lval#7]] specifies that a prvalue appearing as an operand of an operator generally undergoes this conversion; the note in [[class.temporary#2]] lists where materialization happens: binding a reference, member access on a class prvalue or calling an implicit object member function on it, subscripting an array prvalue or applying array-to-pointer conversion to it, constructing a `std::initializer_list`, some operands of `typeid` and `sizeof`, and as a discarded-value expression ([[expr.context#2]]). Conversely, the operand of `decltype` is not materialized, so the type may be incomplete ([[dcl.type.decltype#2]]).

With this, temporary objects have only two sources left ([[class.temporary#1]]): materialization, and the extra objects implementations create for passing and returning, discussed below. The scattered statements in C++14 about creating a temporary object were all deleted or rewritten.

### Initializing from a prvalue of the same type

A new rule was added to initialization, ahead of calling constructors ([[dcl.init#15.6.1]]):

!!! std
    If the initializer expression is a prvalue and the cv-unqualified version of the source type is the same as the destination type, the initializer expression is used to initialize the destination object.

The example the draft attaches here is `T x = T(T(T()));`, which value-initializes `x` only once. At the same time, the item in C++14 [class.copy] ¶31 that allowed eliding the copy of a temporary not bound to a reference was deleted, because that copy no longer exists.

The other subclauses were changed to talk about result objects too:

| Subclause | What it says now |
|---|---|
| [[stmt.return#2]] | `return` copy-initializes the prvalue result object of the call |
| [[expr.call#9]] | The result of a function call is the result of the operand of `return` |
| [[expr.cond#7.1]] | When both operands have the same type, the result is copy-initialized from the selected operand |
| [[expr.type.conv#1]] | `T(args)` and `T{args}` are prvalues whose result object is direct-initialized with the initializer |
| [[expr.prim.lambda.general#2]] | A lambda expression is a prvalue whose result object is called the closure object |

Counting constructions with Clang 23 (destructors after each line omitted):

```cpp run title="count.cpp" ok
#include <cstdio>
struct T {
  T() { std::puts("T()"); }
  T(const T&) { std::puts("T(const T&)"); }
  T(T&&) noexcept { std::puts("T(T&&)"); }
  ~T() { std::puts("~T()"); }
};
T make() { return T(); }
int main() {
  std::puts("[1]"); T a = T(T(T()));
  std::puts("[2]"); T b = make();
  std::puts("[3]"); T c = true ? T() : make();
}
```

| Statement | `-std=c++14 -fno-elide-constructors` | `-std=c++17 -fno-elide-constructors` |
|---|---|---|
| `T a = T(T(T()));` | 1 construction + 3 moves | 1 construction |
| `T b = make();` | 1 construction + 2 moves | 1 construction |
| `T c = true ? T() : make();` | 1 construction + 2 moves | 1 construction |

Without `-fno-elide-constructors`, both modes have just 1 construction. The difference is that in C++14 the result comes from an optimization that can be turned off, while in C++17 it comes from the language rules, and that option can no longer insert moves.

## Consequences

### What is guaranteed and what isn't

```cpp title="limits.cpp"
struct Pinned {
  Pinned() = default;
  Pinned(const Pinned&) = delete;
};
Pinned make() { return Pinned(); }                   // OK: prvalue

Pinned nrvo() { Pinned p; return p; }                // error: NRVO is not guaranteed
Pinned param(Pinned p) { return p; }                 // error: parameters can't be elided
struct AsMember { Pinned m; AsMember() : m(make()) {} };   // OK
struct AsBase : Pinned { AsBase() : Pinned(make()) {} };   // error, see CWG2403

class Hidden { ~Hidden() {} public: Hidden() {} };
Hidden h() { return Hidden(); }   // error: the destructor is private
```

Clang 23 (`-std=c++2c`) reports errors on exactly the four lines marked error.

- `nrvo`: in `return p;`, `p` is implicitly movable and selects a constructor as an xvalue; `Pinned` has no usable move or copy constructor, so it is ill-formed. Eliding this move is only an optimization permitted by [[class.copy.elision#1]] ¶1.1. [[P2025R2]], which would guarantee NRVO, did not make it into the working draft.
- `param`: parameters were never within the scope of elision.
- `AsBase`: by the wording, initializing a base class subobject from a prvalue is no different from initializing a member subobject, but a base class subobject may share tail padding with other members of the derived class, so constructing directly in its place causes problems. [[CWG2403]] records this: implementations all treat the base class case as requiring a copy, while accepting the member case. The issue is still in drafting.
- `Hidden`: the destructor of the result object is potentially invoked ([[stmt.return#3]]) and must be accessible, regardless of whether there is a copy. Materialization likewise requires the destructor to be accessible and not deleted (the note in [[conv.rval#1]]).

So after P0135, factory functions are written as `return T(...);` or `return {...};`, not by constructing a local variable first and returning it. A full comparison of the actual costs is in [[topics/special-members-and-elision]].

### Aggregates and lambdas benefit too

Aggregate members and lambda init-captures are copy-initialized, so initializing them from prvalues needs no constructor either. Closure objects and aggregates themselves are also result objects of prvalues:

```cpp run title="agg-lambda.cpp" ok
#include <atomic>
struct Pinned {
  Pinned(int v) : v(v) {}
  Pinned(const Pinned&) = delete;
  int v;
};
Pinned make(int v) { return v; }
struct Agg { Pinned p; std::atomic<int> n; };
Agg make_agg() { return Agg{make(1), 0}; }   // members and the aggregate itself are constructed directly
int main() {
  Agg g = make_agg();
  auto l = [a = std::atomic<int>(0), p = make(3)]() mutable {
    return ++a + p.v;
  };   // the closure has non-copyable members, and l can still be initialized like this
  return g.p.v + l() - 5;
}
```

Clang 23 compiles and runs this under `-std=c++17`, returning 0; under `-std=c++14`, `make`, `make_agg`, `g` and `l` each report a call to a deleted constructor.

### The exception for trivially copyable types

[[class.temporary#3]] allows implementations to create extra temporary objects when passing and returning, provided the type has eligible copy or move constructors that are all trivial and a destructor that is trivial or deleted. This exception was already in P0135R1, and a note explains that it is there so such objects can be passed in registers. The cost is that the object's address may change on the way back:

```cpp run title="addr.cpp" unspecified
#include <cstdio>
struct Small {                 // trivially copyable
  Small* self;
  Small() : self(this) {}
};
struct Big {                   // user-provided destructor: not trivial
  Big* self;
  Big() : self(this) {}
  ~Big() {}
};
Small make_small() { return Small(); }
Big make_big() { return Big(); }
int main() {
  Small s = make_small();
  Big b = make_big();
  std::printf("Small: %s\n", s.self == &s ? "same" : "different");
  std::printf("Big:   %s\n", b.self == &b ? "same" : "different");
}
```

In our test (arm64, Clang 23, same at `-O0` and `-O2`) it prints `Small: different` and `Big: same`. `Small` is returned in registers, and the `this` during construction is a piece of temporary storage in the callee; `Big` is not allowed to do this, and its constructor runs directly on the caller's `b`. A type whose constructor needs to record `this` should be made not trivially copyable.

### The ABI did not change

P0135 wrote into rules what implementations had long been doing. For types that cannot be returned in registers, the mainstream ABIs already had the caller allocate storage for the return value and pass its address to the callee as a hidden argument. On arm64 at `-O2`, compiling `Pinned make(int v) { return Pinned(v + 1); }` (where `Pinned` has a non-trivial destructor) gives this entire function:

```text
add  w1, w0, #1
mov  x0, x8          // x8: address of the result object passed in by the caller
b    Pinned::Pinned(int)
```

The constructor's `this` is the address the caller provided. With the copy constructor made usable (not deleted), `-std=c++14` and `-std=c++17` generate identical assembly.

### A change not in Annex C

[[diff.cpp14]] has no entry for this change: C++14 already allowed these copies to be elided, so programs depending on the number of copies were never portable. There is, however, one kind of observable difference, in places that ask at compile time whether copy-initialization is possible:

```cpp run title="trait.cpp" ok
#include <type_traits>
struct Pinned {
  Pinned(int) {}
  Pinned(const Pinned&) = delete;
};
static_assert(std::is_convertible<int, Pinned>::value, "");
int main() {}
```

`is_convertible<From, To>` is defined by [[meta.rel#6]] as whether `To test() { return declval<From>(); }` is well-formed. That is exactly the `return v;` above: C++14 has to construct a temporary and then copy, so the result is false; in C++17 it is true. Clang 23 fails this `static_assert` under `-std=c++14` and passes under `-std=c++17`. Code that relies on such checks for overload selection may pick different functions in the two modes.

Another change that came in with P0135R1 concerns when parameters are destroyed: whether a parameter is destroyed when the function returns or at the end of the full-expression containing the call became implementation-defined ([[expr.call#7]]).

### Remaining issues

- [[CWG2327]]: `Cat c(d);`, where the type of `d` has a conversion function returning `Cat`. This is direct-initialization, and by [[dcl.init#15.6.2]] only the constructors of `Cat` are considered; the parameter of the copy or move constructor binds to the result of the conversion function, so a temporary is materialized and then copied, and the guarantee falls through. [[P2828R2]] proposes considering conversion functions as well.
- [[CWG2403]]: base class subobjects, see above.

```cpp title="cwg2327.cpp"
struct Cat { Cat() {} Cat(const Cat&) = delete; };
struct Dog { operator Cat() const { return Cat(); } };
int main() {
  Dog d;
  Cat a = d;   // copy-initialization: the conversion function's result initializes a directly
  Cat b(d);    // direct-initialization: by the current wording, selects the deleted copy constructor
}
```

By the current wording the second line is ill-formed; Clang 23 accepts both lines, and with `-fno-elide-constructors` it prints no copy or move for a version with side effects either, effectively already following the direction of the issue. Code that depends on this, such as passing a lazy wrapper with a conversion function to `std::optional<T>::emplace` to construct a non-movable `T` in place, works on Clang but has no basis in the standard yet.

### Compiler support

The feature-test macro is `__cpp_guaranteed_copy_elision`, with the value `201606L` ([[cpp.predefined]]). Clang 23 defines it under `-std=c++17` and above, and not under `-std=c++14`. All examples on this page were verified with Clang 23.

The full model of value categories is in [[topics/value-categories]], and where this change sits in the evolution of move semantics is in [[history/move-semantics]].

## Questions

!!! question "1"
    Does `std::atomic<int> f() { std::atomic<int> a(0); return a; }` compile in C++17? What about changing it to `return std::atomic<int>(a.load());`?

<details markdown="1">
<summary>Answer</summary>

The former does not. `return a;` returns a named variable, and `a` initializes the result object as an xvalue, which needs a move or copy constructor; `std::atomic` has neither, and NRVO is only a permitted elision ([[class.copy.elision#1]]) that does not waive this check. The latter works: the operand is a prvalue of the same type, which by [[dcl.init#15.6.1]] directly initializes the result object of the call.
</details>

!!! question "2"
    Given `struct P { std::mutex m; };`, how many `P` objects do `const P& r = P();` and `P p = P();` each create? Which one has a temporary object?

<details markdown="1">
<summary>Answer</summary>

One each. In `P p = P();` the result object of `P()` is `p`, and there is no temporary. In `const P& r = P();` the reference must bind to a glvalue, so `P()` goes through temporary materialization ([[conv.rval#1]]) and becomes a temporary object, whose lifetime is extended to match `r` ([[class.temporary]]). Neither needs a copy or move constructor of `P`.
</details>

!!! question "3"
    Why is `T x = T(T(T()));` guaranteed to construct only once in C++17, while `T x = static_cast<T&&>(T());` is not?

<details markdown="1">
<summary>Answer</summary>

In the former, every level is a prvalue of the same type initializing an object of the same type, and the result object is passed all the way down to `x`. In the latter, `static_cast<T&&>` must bind a reference to `T()`, so a temporary is materialized and the expression becomes an xvalue; `x` is then move-constructed from that xvalue, for two objects in total. Only prvalues pass the result object down; any wrapper that produces a glvalue breaks the chain.
</details>
