---
title: Copy/move elision
summary: "Where an implementation may omit a copy or move (NRVO, throw, coroutine parameters, catch) even if the constructor has side effects; how this differs from C++17 prvalues, which never produce a copy at all; the implicit move when NRVO doesn't happen; and why elision is not allowed in constant evaluation."
updated: 2026-10-19
---

!!! tldr
    - Forms that initialize from a prvalue, like `return T(...);` and `T x = f();`, involve no copy at all since C++17; the copy and move constructors needn't even exist.
    - The copy in `T t; ...; return t;` may be elided (NRVO), but this isn't guaranteed, so a copy or move constructor must be usable. When it is elided, the constructor's side effects disappear with it.
    - When NRVO doesn't happen, `return local_variable;` moves automatically instead of copying; `return std::move(local);` actually prevents NRVO.
    - There are only four contexts where elision is permitted: `return` of a local object, `throw` of a local object, a coroutine copying its parameters, and `catch` by value.
    - Elision isn't allowed in constant evaluation, so `constexpr` results don't depend on whether the compiler performed this optimization.

## Two different kinds of copy elision

```cpp run title="no-copy-at-all.cpp" ok
struct NM {
  NM() {}
  NM(const NM&) = delete;   // not copyable
  NM(NM&&) = delete;        // not movable either
};

NM make()  { return NM(); }
NM make2() { return {}; }

int main() {
  NM a = make();            // OK
  NM b = NM(NM(NM()));      // OK: constructed only once
  auto c = make2();         // OK
  (void)a; (void)b; (void)c;
}
```

`NM` can be neither copied nor moved, yet this code is valid since C++17. The reason is that expressions like `NM()` and `make()` are **prvalues** ([[g:prvalue]]): not objects, but descriptions of how to initialize an object; the object a prvalue initializes is its **result object** ([[g:result-object|result object]], [[basic.lval#5]]). When an object is initialized from a prvalue of the same type, the target object is the result object ([[dcl.init#15.6.1]]), with no temporary in between and no copy.

Compiled with `-std=c++14`, every one of these except the `return {};` in `make2` is reported as calling a deleted constructor. In C++14 these places semantically involved temporaries and copies that implementations were merely allowed to elide, so the constructors had to be usable.

Returning a named local variable is a different matter:

```cpp error
struct NM {
  NM() {}
  NM(NM&&) = delete;
};
NM bad() {
  NM n;
  return n;   // error: needs a move constructor
}
```

Here there really is an initialization from `n` to the return value. This subclause, [class.copy.elision], permits the implementation to omit it but doesn't require it, so the constructor must exist and be accessible. The two cases compare as follows:

| | Initialization from a prvalue | Permitted copy elision (this subclause) |
|---|---|---|
| Example | `return T(...);`, `T x = f();` | `T t; return t;` (NRVO) |
| In substance | No copy at all | There is a copy or move, which the implementation may omit |
| Guaranteed? | Yes, part of the language semantics | No, up to the implementation |
| Copy/move constructor | Not needed | Must be usable |
| In constant evaluation | As usual | Elision not allowed |

The left column is often called guaranteed copy elision, but the standard has no such term: C++17's [[P0135R1]] took it out of copy elision and made it part of the semantics of prvalues. The standard has no elided copy there, only a copy that never happens.

The left column also has two exceptions that do produce temporaries. One is **temporary materialization**: binding a prvalue to a reference, accessing a member of it and so on turn it into a temporary object ([[class.temporary#2]]). The other is small trivially copyable types: [[class.temporary#3]] allows implementations to create extra temporaries for passing and returning them, so small structs can be passed in registers, at the cost of the object's address changing.

## Permitted copy elision (¶1)

```cpp run title="thing.cpp" ok
#include <cstdio>

class Thing {
public:
  Thing()             { std::puts("Thing()"); }
  ~Thing()            { std::puts("~Thing()"); }
  Thing(const Thing&) { std::puts("Thing(const Thing&)"); }
};

Thing f() {
  Thing t;
  return t;     // the copy may be elided: t is constructed directly as t2
}

Thing t2 = f();

int main() { std::puts("main"); }
```

Clang 23 prints `Thing()`, `main`, `~Thing()`; the output from the copy constructor doesn't appear. This is a runnable version of Example 1 in the standard (¶2): the construction of `t` can be viewed as directly initializing `t2`, and that object is destroyed at program exit. Adding a move constructor to `Thing` gives the same result, except that what's elided is a move.

¶1 When certain criteria are met, an implementation is allowed to omit the creation of a class object from a source object of the same type (ignoring cv-qualification), even if the selected constructor or the destructor has side effects. The source and target are then just two ways of referring to the same object. This is called **copy elision** ([[g:copy-elision|copy elision]]).

!!! std
    In such cases, the implementation treats the source and target of the omitted initialization as simply two different ways of referring to the same object.

Ordinary optimizations are bound by the as-if rule ([[intro.abstract]]) and may be performed only if observable behavior doesn't change. Copy elision is one of the few optimizations explicitly allowed to change observable behavior: the `puts` in the copy constructor may not run.

### When the merged object is destroyed

Two objects merged into one leaves only one destruction. If the first parameter of the selected constructor is an rvalue reference to the type (that is, it would have been a move), the merged object is destroyed when the target would have been destroyed; otherwise it is destroyed at the later of the times when the two objects would have been destroyed. Note 1 points out that one fewer object is constructed and one fewer is destroyed, so constructions and destructions still correspond one to one.

### The four permitted contexts

¶1.1 **`return` statements**: in a function with a class return type, if the operand of `return` is the name of a non-volatile object *o* with automatic storage duration, *o* can be constructed directly in the result object of the function call. This is what is usually called **NRVO** (named return value optimization). The conditions are fairly strict:

- It must be a name, possibly parenthesized; `return c ? x : y;`, `return std::move(x);` and `return p.a;` don't qualify;
- It must be an object with automatic storage duration; `static` local variables, references and structured bindings don't qualify;
- It can't be a function parameter or a variable declared in a `catch` clause. A parameter is constructed by the caller, and the callee has no way to put it where the return value goes.

¶1.2 **`throw` expressions**: when the operand is a local object *o* meeting the same conditions, and the scope of *o* does not contain the innermost enclosing `try` block's compound statement, *o* can be constructed directly as the exception object. If `throw x;` is inside a `try` block within `x`'s scope, the exception may be caught by that `try` and the code may use `x` afterwards, so `x` and the exception object have to be two objects.

¶1.3 **Coroutines**: a coroutine copies its parameters into the coroutine frame ([[dcl.fct.def.coroutine]]). If the meaning of the program is unchanged except for the construction and destruction of the copy, the copy can be omitted, and references to the copy become references to the original parameter.

¶1.4 **`catch` clauses**: when a *handler* declares an object *o*, if the meaning of the program is unchanged except for the construction and destruction of *o*, *o* can be treated as an alias of the exception object. Note 2 points out that there can't be a move here, because the exception object is always an lvalue.

These contexts can be combined to omit several copies at once.

## When NRVO doesn't happen: implicit move (¶3)

When the implementation doesn't elide `return t;`, which constructor initializes the return value? Since C++23, the answer is given by [[expr.prim.id.unqual#15]]:

- An **implicitly movable entity** is a variable with automatic storage duration that is either a non-volatile object or an rvalue reference to a non-volatile object type;
- If a name refers to such an entity, is the operand (possibly parenthesized) of `return`, `co_return` or `throw`, and only block scopes intervene between the entity's declaration and the expression (for `throw`, not the scope of a `try` block either), the expression is **move-eligible** ([[g:move-eligible]]);
- A move-eligible expression is an xvalue ([[expr.prim.id.unqual#12]]), so overload resolution prefers the move constructor.

¶3 is Example 2 in the standard:

```cpp title="implicit-move.cpp" error
class Thing {
public:
  Thing();
  ~Thing();
  Thing(Thing&&);
private:
  Thing(const Thing&);
};

Thing f(bool b) {
  Thing t;
  if (b)
    throw t;     // OK: uses (or elides) Thing(Thing&&)
  return t;      // OK: uses (or elides) Thing(Thing&&)
}

Thing t2 = f(false);   // OK: t2 is constructed by the call to f

struct Weird {
  Weird();
  Weird(Weird&);
};

Weird g(bool b) {
  static Weird w1;
  Weird w2;
  if (b)
    return w1;   // OK: static variables aren't implicitly moved; uses Weird(Weird&)
  else
    return w2;   // error: w2 is an xvalue and can't bind to Weird&
}

int& h(bool b, int i) {
  static int s;
  if (b)
    return s;    // OK
  else
    return i;    // error: i is an xvalue; int& can't bind to it
}

decltype(auto) h2(Thing t) {
  return t;      // OK: decltype(t) is Thing, return type Thing
}

decltype(auto) h3(Thing t) {
  return (t);    // OK: (t) is an xvalue, return type Thing&&
}
```

- `throw t;` and `return t;` both select the move constructor; it doesn't matter that the copy constructor is `private`.
- `return w2;` is an incompatible change brought by C++23's [[P2266R3]]. C++20 first did overload resolution treating the operand as an rvalue, and if that failed, did it again treating it as an lvalue, where `Weird(Weird&)` could match. Since C++23 it is simply an xvalue, and there is no second attempt. Clang accepts it with `-std=c++20` and rejects it with `-std=c++23` and later.
- `return i;` returns a reference to a parameter, which inevitably dangles. Since C++23 it is ill-formed outright; under C++20 Clang only gives a `-Wreturn-stack-address` warning.
- In `h3`, `decltype(auto)` deduces `Thing&&` from `(t)` ([[dcl.type.decltype]]), and the returned reference refers to the parameter, so it dangles too. It is well-formed, but shouldn't be written.

Implicit move and copy elision are two layers of mechanism: the former decides which constructor to use when the return value needs initializing, and the latter decides whether that initialization can be omitted. As long as the expression is move-eligible, what you get when NRVO doesn't happen is a move, not a copy.

### `throw` and `try` blocks (¶4)

¶4 is Example 3 in the standard:

```cpp title="throw-scope.cpp" error
template<class T> void g(const T&);

template<class T> void f() {
  T x;
  try {
    T y;
    try { g(x); }
    catch (...) {
      if (/*...*/ true)
        throw x;   // does not move
      throw y;     // moves
    }
    g(y);
  } catch (...) {
    g(x);
    g(y);          // error: y is not in scope
  }
}
```

Between the declaration of `x` and `throw x;` lies the scope of the outer `try` block, so `x` is not move-eligible and can only be copied. That is what's needed: after the exception is caught by the outer `catch`, `g(x)` still uses `x`. `y` is declared inside the outer `try` block, and only the `catch` clause's block scope lies between it and `throw y;`, so it is moved. By the time the exception leaves the outer `try` block, `y` has been destroyed, so taking its resources is fine.

## No elision in constant evaluation

¶1 ends by saying that copy elision is not permitted in a context that requires a constant expression ([[expr.const.const]]) or in constant initialization ([[basic.start.static]]). Note 3 adds that the same expression evaluated in another context may still have the copy elided.

```cpp title="constexpr-elision.cpp" error
struct A {
  void* p;
  constexpr A() : p(this) {}   // records its own address
};

constexpr A g() {
  A loc;
  return loc;
}

constexpr A a;          // OK: a.p points to a
constexpr A b = g();    // error: b is a copy of loc, and b.p dangles
void h() {
  A c = g();            // OK: c.p may point to c, or may dangle
}
```

This is the second half of Example 1 in the standard. `A` records its own address, which makes it possible to observe whether the copy was elided. If constant evaluation allowed elision, the value of `b.p` would depend on the compiler's choice; with it forbidden, the result is definite: `b` is a copy of `loc`, and `b.p` points to `loc`, whose lifetime has ended, so it can't be the result of a constant expression. Clang's accompanying note is `pointer to 'loc' is not a constant expression`.

For `c` in `h`, both results are allowed at run time. Clang gets `c.p != &c` at both `-O0` and `-O2`: `A` is an 8-byte trivially copyable type returned in registers per [[class.temporary#3]], so `loc` and `c` are necessarily two objects.

Using a prvalue avoids the problem, because there is no copy at all:

```cpp run title="constexpr-ok.cpp" ok
struct A {
  void* p;
  constexpr A() : p(this) {}
};

constexpr A mk() { return A(); }   // prvalue, no copy
constexpr A c = mk();
static_assert(c.p == &c);          // c is the result object of A()

int main() {}
```

## What compilers actually do

```cpp run title="observe.cpp" ok
#include <cstdio>

struct T {
  T()             { std::puts("  T()"); }
  T(const T&)     { std::puts("  T(const T&)"); }
  T(T&&) noexcept { std::puts("  T(T&&)"); }
  ~T()            { std::puts("  ~T()"); }
};

T make()      { return T(); }          // prvalue
T nrvo()      { T t; return t; }       // NRVO possible
T two(bool b) { T x, y; if (b) return x; return y; }
T param(T p)  { return p; }            // parameter

int main() {
  std::puts("make:");  { T a = make(); }
  std::puts("nrvo:");  { T b = nrvo(); }
  std::puts("two:");   { T c = two(true); }
  std::puts("param:"); { T d = param(T()); }
}
```

Constructor calls (not counting destructors) with Clang 23 at `-O0`:

| Function | C++26 | C++26, `-fno-elide-constructors` | C++14, `-fno-elide-constructors` |
|---|---|---|---|
| `make()` | `T()` | `T()` | `T()` + 2 moves |
| `nrvo()` | `T()` | `T()` + 1 move | `T()` + 2 moves |
| `two(true)` | 2 × `T()` + 1 move | Same | 2 × `T()` + 2 moves |
| `param(T())` | `T()` + 1 move | Same | `T()` + 3 moves |

- `-fno-elide-constructors` (in both GCC and Clang) turns off permitted elision. In C++17 and later, `make()` is unaffected because there was never a copy there; only `nrvo()` gains a move. Under C++14 all the temporaries show up.
- `two`: either local variable might be returned, and the compiler can't decide in advance which one to place where the return value goes, so NRVO fails and falls back to implicit move.
- `param`: a parameter can't get NRVO, but it is implicitly moved.
- Clang performs NRVO even at `-O0`; it decides in the front end, independent of optimization level. `return (t);` with parentheses also gets NRVO.

Although `throw` and `catch` also permit elision, Clang does neither:

```cpp run title="throw-catch.cpp" ok
#include <cstdio>

struct T {
  T()             { std::puts("  T()"); }
  T(const T&)     { std::puts("  T(const T&)"); }
  T(T&&) noexcept { std::puts("  T(T&&)"); }
  ~T()            { std::puts("  ~T()"); }
};

void f1() { T t; throw t; }

int main() {
  try { f1(); } catch (T e) { std::puts("  in handler"); }
  // T() / T(T&&) / ~T() / T(const T&) / in handler / ~T() / ~T()
}
```

`throw t;` moves `t` into the exception object. The exception object is allocated on the heap by the runtime library (`__cxa_allocate_exception`) and can't share storage with `t` on the stack. `catch (T e)` copies `e` from the exception object, because the exception object is an lvalue. Hence the usual advice to throw by value and catch by `const&`.

!!! impl "Where the return value lives"
    Under the Itanium C++ ABI, a function returning a non-trivial class type receives a hidden parameter: the address of the result object the caller has prepared (passed in `x8` on AArch64; on x86-64 System V passed in `rdi` and returned in `rax`). `return T(...);` constructs directly at that address; NRVO places the local variable `t` at that address, so `return t;` has nothing to do; in `two`, `x` and `y` can't both live at the same address, so it fails.

    Small trivially copyable types are returned in registers per the ABI, so there is no result object address to pass, and the result object is necessarily a different object in the caller. That is why [[class.temporary#3]] allows extra temporaries.

!!! impl "Related warnings"
    Clang's `-Wall` includes these two warnings. `-Wpessimizing-move`: `return std::move(local);` prevents NRVO. `-Wredundant-move`: a `std::move` written where an implicit move would happen anyway, as in `T d(T p) { return std::move(p); }`.

!!! history
    - C++98 already allowed eliding copies in `return` and in `throw`/`catch`, even with side effects; the elided copy constructor still had to be accessible.
    - C++11 introduced move semantics and specified that a `return`/`throw` eligible for copy elision first performs overload resolution treating the operand as an rvalue; this was the beginning of implicit move. [[CWG1579]] extended it to cases where the return type differs from the local variable's type, for example a local `unique_ptr<Derived>` with return type `unique_ptr<Base>`.
    - C++17's [[P0135R1]] made prvalues no longer produce copies, leaving only permitted elision in this subclause.
    - C++20's [[P1825R0]] allowed local variables of rvalue reference type to be implicitly moved too, and removed the requirement that the selected constructor's parameter be an rvalue reference.
    - C++23's [[P2266R3]] made move-eligible names xvalues outright, eliminating the two-step overload resolution; returning an lvalue reference to a local variable therefore became ill-formed.

## Common misconceptions

!!! pitfall "`return std::move(local);` is faster"
    `std::move(local)` is not a name, so item 1.1 doesn't apply and NRVO can't happen, giving an extra move that could have been avoided. Just write `return local;`; even without NRVO it is implicitly moved.

!!! pitfall "`return cond ? a : b;` moves"
    A conditional expression is not a name, so it gets neither NRVO nor implicit move (it is an lvalue), and the result is a copy. Rewriting it as `if (cond) return a; return b;` at least guarantees a move.

!!! pitfall "Returning a member, a structured binding or `*this` moves"
    `return p.a;`, `auto [a, b] = ...; return a;` and `return *this;` are not move-eligible: a member access doesn't name a variable, and a structured binding isn't a variable. They all copy; write `std::move` explicitly when you want a move.

!!! pitfall "NRVO always happens, so no move constructor is needed"
    NRVO is permitted, not guaranteed. For a non-movable type, `NM n; return n;` is still ill-formed. Only returning a prvalue removes the requirement for a constructor.

!!! pitfall "Relying on the copy constructor's side effects"
    Counting, logging or registering objects in a copy constructor is unreliable; whether NRVO happens depends on the compiler and the code structure. A copy constructor should only copy.

## Questions

!!! question "1. Which of these three functions can get NRVO? Without NRVO, which constructor does each call? (`T` as in `observe.cpp`)"
    ```cpp nocheck
    T a()      { T t; return (t); }
    T b()      { static T t; return t; }
    T c(T&& r) { return r; }
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: `(t)` is a parenthesized name. A parenthesized expression is exactly equivalent to the expression inside ([[expr.prim.paren]]), and Clang and GCC both apply NRVO to it; even without it, [[expr.prim.id.unqual#15.2]] explicitly allows parentheses, so it moves.
- `b`: static storage duration, so no NRVO, and it isn't an implicitly movable entity, so it copies. Clang prints `T(const T&)`.
- `c`: `r` is an automatic variable of rvalue reference type, which since C++20 is an implicitly movable entity, so it moves. It is a reference rather than an object, so it can't get NRVO.
</details>

!!! question "2. How many constructor calls does `T x = T(T(T()));` make in C++14 and in C++17?"

<details markdown="1">
<summary>Answer</summary>

C++14: semantically one default construction plus three moves, all of which may be elided, so in practice anywhere from 1 to 4, and the move constructor must be usable. C++17: just one default construction. `T(prvalue)` is still the same prvalue, and `x` is the result object of the innermost `T()` ([[dcl.init#15.6.1]]); copies and moves never happen, so they may even be deleted.
</details>

!!! question "3. Why can't NRVO be used for function parameters, when parameters can be implicitly moved?"

<details markdown="1">
<summary>Answer</summary>

NRVO means having a local variable live directly in the result object's storage. A parameter's storage is allocated and initialized by the caller before the call (in the Itanium ABI, a parameter of non-trivial type is a temporary in the caller's stack frame), and the callee can't make it coincide with the return value location the caller provides. Implicit move only changes the outcome of overload resolution and places no requirements on storage location; the parameter is destroyed right after the function returns, so taking its resources is safe.
</details>
