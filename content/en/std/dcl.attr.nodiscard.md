---
title: Nodiscard attribute
summary: "[[nodiscard]] on a function, constructor, class or enumeration makes the compiler warn when a result is simply discarded; it only affects diagnostics, and (void) expresses an intentional discard."
updated: 2026-10-19
---

!!! tldr
    - `[[nodiscard]]` is for cases where ignoring a result is almost certainly a mistake: an unchecked error code, a lock guard destroyed right after construction. It only makes the compiler warn and doesn't change the program's meaning.
    - It can be applied to functions, lambdas and constructors, and to class or enumeration types; on a type, it takes effect for every function returning that type by value.
    - Functions returning `E&` or `E*` aren't warned about just because `E` is nodiscard; mark the function itself.
    - It only warns when the result is directly discarded; write `(void)f();` or `std::ignore = f();` to discard intentionally.
    - The attribute can be added in a later redeclaration, but once added it can't be removed.

## A lock that forgot its name

```cpp run ok
struct [[nodiscard]] Error { int code; };
Error save();                      // returns a nodiscard type

struct Lock {
  [[nodiscard]] explicit Lock(int fd) { (void)fd; }
};

void f() {
  save();                          // warning: the error code is discarded
  Lock(3);                         // warning: the temporary is destroyed immediately
  Lock lk(3);                      // OK: this is what was meant
  (void)lk;
}
int main() {}
```

`Lock(3);` is a common mistake: the intent was `Lock lk(3);`, but only a temporary is constructed, which locks and immediately unlocks. `save();` throws away an error code. Both lines compile and have no undefined behavior; they're just almost certainly wrong. `[[nodiscard]]` makes the compiler warn in such places. Clang 23 warns `ignoring return value of type 'Error' declared with 'nodiscard' attribute` and `ignoring temporary created by a constructor declared with 'nodiscard' attribute` for the two lines respectively.

This attribute only affects diagnostics. The standard only specifies when implementations are encouraged to warn, with no effect on program execution, satisfying the ignorability of [[dcl.attr.grammar#8]].

## Where it can go (¶1–¶2)

```cpp run ok
[[nodiscard]] int compute();                            // function
[[nodiscard("check the error code")]] int open_file();  // with a reason
struct [[nodiscard]] Error { int code; };               // class
enum class [[nodiscard]] Errc { ok, bad };              // enumeration

struct Lock {
  [[nodiscard]] explicit Lock(int fd);                  // constructor
  Lock();                                               // this one isn't
};

auto l = [] [[nodiscard]] () { return 1; };             // lambda
int main() {}
```

¶1 `nodiscard` can be applied to functions (including constructors, C++20's [[P1771R1]]), lambda call operators (C++23's [[P2173R1]]), and declarations of classes or enumerations. It can take a string argument giving a reason (C++20's [[P1301R4]]), which compilers should include in the warning.

¶2 A function or type can first be declared without the attribute and have it added in a later redeclaration; Note 1 explains that once added, later redeclarations can't remove it. The reasons given by different declarations may differ.

```cpp run ok
int f();
[[nodiscard]] int f();   // from here on f is nodiscard
int f();                 // can't remove it
int main() {}
```

This differs from `[[noreturn]]`, which must appear on the first declaration because it affects code generation at call sites. `nodiscard` only affects diagnostics, so learning about it later is fine.

## Which calls are nodiscard calls (¶3)

¶3 first defines two terms. A [[g:nodiscard-type|nodiscard type]] is a class or enumeration type marked `nodiscard` in some reachable declaration, possibly with `const` or `volatile`. A [[g:nodiscard-call|nodiscard call]] is one of the following two kinds of expression:

- ¶3.1 a function call expression ([[expr.call]]) whose called function is marked `nodiscard` or whose return type is a nodiscard type;
- ¶3.2 an explicit type conversion such as `T(x)`, `T{x}`, `static_cast<T>(x)` or `(T)x` ([[expr.type.conv]], [[expr.static.cast]], [[expr.cast]]) that constructs an object through a constructor marked `nodiscard`, or that initializes an object of a nodiscard type.

A few things to note:

1. The return type must be the nodiscard type itself. A function returning `Error&`, `Error*` or `std::optional<Error>` is not a nodiscard call unless it is marked `nodiscard` itself.
2. When calling through a function pointer, the compiler only sees the pointer's type. Real compilers judge only by the return type and won't warn just because the pointer points to a function marked `nodiscard`.
3. The constructor case only covers the explicit type conversion kind of expression. `Lock lk(3);` is a declaration, not an expression, so discarding doesn't arise.

## When a warning is encouraged (¶4)

!!! std
    Appearance of a nodiscard call as a potentially evaluated discarded-value expression ([expr.prop]) of non-void type is discouraged unless explicitly cast to `void`.

¶4 When a nodiscard call appears in a position like the following, the standard recommends that implementations warn, including the reason string:

- it is a **discarded-value expression** ([[expr.context]]), i.e. an expression whose result isn't used: an expression statement `f();`, the left operand of the comma operator, the init-statement and increment expression of a `for`, and so on;
- it is potentially evaluated, so the `f()` in `sizeof(f())` or `decltype(f())` doesn't count;
- its type is not `void`;
- it isn't explicitly cast to `void`. `(void)f();` and `static_cast<void>(f());` are the accepted ways to express an intentional discard.

Implementations that can't issue such warnings should report 0 for `__has_cpp_attribute(nodiscard)`.

```cpp run ok
#include <tuple>
[[nodiscard]] int f();
struct [[nodiscard]] R {};
R make();
R& get();

void t() {
  f();                      // warning
  make();                   // warning: returns a nodiscard type
  R{};                      // warning: initializes an object of nodiscard type (¶3.2)
  (void)f();                // no warning: explicit discard
  std::ignore = f();        // no warning: the result is used
  get();                    // no warning: returns a reference
  int (*fp)() = f;
  fp();                     // no warning: called through a pointer
  (void)sizeof(f());        // no warning: not potentially evaluated
  for (f();;) break;        // warning: discarded in the init-statement
}
int main() {}
```

All the comments above match the actual behavior of Clang 23. `std::ignore = f();` officially became a valid way to discard intentionally in C++26 (the assignment behavior of `std::ignore` is now specified); it stands out more than `(void)` and is easier to search for.

### The standard's example

The example in ¶5 puts several cases together:

```cpp run ok
struct [[nodiscard]] my_scopeguard { };
struct my_unique {
  my_unique() = default;                         // doesn't acquire a resource
  [[nodiscard]] my_unique(int fd) { (void)fd; }  // acquires a resource
  ~my_unique() noexcept { }                      // releases the resource, if any
};
struct [[nodiscard]] error_info { };
error_info enable_missile_safety_mode() { return {}; }
void launch_missiles() {}

void test_missiles() {
  my_scopeguard();               // warning encouraged
  (void)my_scopeguard(),         // warning not encouraged: cast to void
    launch_missiles();           // comma operator; the statement isn't over yet
  my_unique(42);                 // warning encouraged: nodiscard constructor
  my_unique();                   // warning not encouraged: this constructor isn't marked
  enable_missile_safety_mode();  // warning encouraged
  launch_missiles();
}
error_info& foo() { static error_info e; return e; }
void f() { foo(); }              // warning not encouraged: returns a reference
int main() { test_missiles(); f(); }
```

The difference between `my_unique(42)` and `my_unique()` shows why marking constructors is useful: only for the constructor that acquires a resource is it worth warning when the temporary is discarded.

## Where it fits

- Functions returning error codes or status. Better still, mark the error type itself: mark it once, and it takes effect for every function returning it by value.
- Functions called only for their return value: `empty()`, `size()`, `std::launder`, `operator new`. `v.empty();` is often `empty` mistaken for `clear`.
- Constructors and factory functions that acquire resources: `std::make_unique`, `std::allocator::allocate`; discarding the result is a leak.
- Functions that return a new object rather than modifying the original, such as `trimmed()`-style interfaces, which users easily assume modify in place.

Since C++20, the standard library specification marks `operator new`, `allocate`, containers' `empty()`, `std::launder` and others with `[[nodiscard]]` ([[P0600R1]]). The three major standard library implementations use it far more than the standard requires.

!!! impl "Compiler warnings"
    - Clang: discarding the result of a call to a function marked `nodiscard` reports `-Wunused-result`; discarding a returned nodiscard type or a temporary from a nodiscard constructor reports `-Wunused-value`. Both are on by default. When `[[nodiscard]]` is on a function returning `void`, Clang warns that the attribute is ignored.
    - GCC uses `-Wunused-result` throughout, on by default. GCC's `__attribute__((warn_unused_result))` is its predecessor, but that attribute's warning can't be silenced with `(void)`; the standard attribute improves on this.
    - MSVC reports warnings such as C4834.
    - The warning is recommended practice, not a requirement; implementations may skip it in templates or macro expansions to reduce noise.

## History

!!! history
    - C++17: `[[nodiscard]]` introduced ([[P0189R1]], derived from [[P0068R0]]), only for functions, classes and enumerations, with no argument.
    - C++20: can carry a reason ([[P1301R4]]), can be applied to constructors ([[P1771R1]]), and the standard library started using it ([[P0600R1]]).
    - C++23: lambda call operators can have attributes ([[P2173R1]]).
    - C++26: strings in attribute arguments became unevaluated strings ([[P2361R6]]), and implementations that can't warn must make `__has_cpp_attribute` return 0. The current draft states the rules in terms of nodiscard types and nodiscard calls.

## Common misconceptions

!!! pitfall "nodiscard forces the result to be checked"
    It doesn't make the program ill-formed, and doesn't even guarantee a warning. To enforce it, rely on type design (such as a result type that checks on destruction whether it was read) or contracts.

!!! pitfall "`std::lock_guard<std::mutex>(m);` just lacks a name"
    This line isn't an expression at all. By [[dcl.ambig.res]] it declares a local variable named `m` that hides the outer mutex. `lock_guard` isn't default-constructible, so it usually fails to compile, but other types may pass silently. A nodiscard constructor doesn't help here; write `std::lock_guard lk(m);`.

## Questions

!!! question "Question"
    Per ¶3–¶4, which lines below should get a warning?
    ```cpp
    struct [[nodiscard]] R {};
    R make();
    const R cmake();
    R* pmake();
    [[nodiscard]] void v();
    void t() {
      make();
      cmake();
      pmake();
      v();
      R r = make();
    }
    ```

<details markdown="1">
<summary>Answer</summary>

- `make();`: returns a nodiscard type and the result is discarded; a warning is encouraged.
- `cmake();`: a nodiscard type can carry `const`; a warning is encouraged.
- `pmake();`: returns `R*`, which isn't a nodiscard type, and the function isn't marked; no warning encouraged.
- `v();`: the function is marked, but the expression has type `void`, and ¶4 only covers non-`void` cases; no warning encouraged. Clang warns about the declaration itself that the attribute is ignored.
- `R r = make();`: the result initializes `r`, so it isn't a discarded-value expression; no warning encouraged.

Clang 23's actual warnings agree with the above.
</details>
