---
title: The constinit specifier
summary: "constinit requires a variable with static or thread storage duration to be initialized during static initialization and makes it an error otherwise; it doesn't make the variable const, doesn't require compile-time destruction, and must appear on the initializing declaration."
updated: 2026-10-19
---

!!! tldr
    - `constinit` applies only to variables with static or thread storage duration and requires their initialization to be constant initialization, i.e. no code has to run at program startup.
    - Whether it is constant initialization is decided by the standard's rules; it doesn't count if the compiler could optimize some dynamic initialization into static initialization.
    - A `constinit` variable is not const: it can be modified and can have a non-trivial destructor. That is the main difference from `constexpr`.
    - If any declaration has `constinit`, the initializing declaration must have it too; if this is violated but no `constinit` declaration is visible in the current translation unit, no diagnostic is required.

## What problem it solves

Initialization of variables with static or thread storage duration falls into two kinds ([[basic.start]]):

- **Static initialization**: zero-initialization, or **constant initialization** (the initializer is a constant expression, [[expr.const.init]]). It completes before all dynamic initialization and is usually just ready-made bytes in the object file's `.data` or `.rodata` section; no code runs.
- **Dynamic initialization**: everything else, which runs code at program startup (or before first use). Across translation units (TUs), the order of dynamic initialization is indeterminate.

If the dynamic initialization of a global variable in TU A reads a global variable in TU B that has not been dynamically initialized yet, it reads a zero value. This is the **static initialization order fiasco**. Whether a variable is constant-initialized often depends on obscure details such as whether some constructor is constexpr or whether some call can be constant-evaluated, and a single change can silently turn it into dynamic initialization. `constinit` (C++20, [[P1143R2]]) turns this property into a declaration the compiler must check.

## Only for variables with static or thread storage duration (¶1)

```cpp run ok
constinit int counter = 0;                      // namespace scope: static storage duration
constinit thread_local int tls_counter = 0;     // thread storage duration
struct S { static constinit int m; };
constinit int S::m = 42;
int f() { static constinit int calls = 0; return ++calls; }   // block-scope static
struct P { int a, b; };
constinit auto [pa, pb] = P{1, 2};              // structured binding
int main() { return f() + counter + tls_counter + S::m + pa + pb - 46; }
```

¶1 `constinit` can be applied only to declarations of variables with static or thread storage duration and to structured binding declarations. Note 1 says that for a structured binding it applies to the hidden variable the structured binding introduces ([[dcl.struct.bind]]).

```cpp error
void g() { constinit int x = 1; }   // error: automatic storage duration
constinit void h();                 // error: not a variable
```

An automatic variable is reinitialized every time its scope is entered; there is no static initialization phase and so no initialization order problem. To require a local variable's initializer to be a constant expression, use `constexpr`.

### Must appear on the initializing declaration

The second half of ¶1 says that if any declaration of a variable has `constinit`, its **initializing declaration** (the declaration with the initializer, or the one that is a definition, [[dcl.init]]) must have it too. The typical use is a declaration in a header and the definition in a source file:

```cpp title="config.h"
extern constinit int max_connections;    // tells users: it is statically initialized
```

```cpp title="config.cpp"
#include "config.h"
constinit int max_connections = 64;      // initializing declaration: must have constinit
```

Only at the initializing declaration does the compiler see the initializer and can check it. If a reachable `constinit` declaration precedes it but the initializing declaration lacks it, the program is ill-formed:

<div class="compare" markdown="1">

```cpp error
extern constinit int y;
int y = 1;   // error: missing constinit
             // (Clang only warns)
```

```cpp run ok
extern int z;
constinit int z = 1;   // OK
int main() { return z - 1; }
```

</div>

The reverse is allowed: earlier declarations without it, and only the initializing declaration with it.

If no `constinit` declaration is reachable at all at the initializing declaration, no diagnostic is required {{ifndr}}:

```cpp title="a.cpp"
extern constinit int x;      // only a.cpp has a constinit declaration
int use() { return x; }      // the compiler may assume x is statically initialized
```

```cpp title="b.cpp"
int compute();
int x = compute();           // the initializing declaration lacks constinit, and none is visible in this TU
```

When compiling b.cpp the compiler doesn't know there is a `constinit` declaration elsewhere and can't diagnose it; when compiling a.cpp it has already generated code assuming x is statically initialized. This violation can't be detected within a single TU, so it is **ill-formed, no diagnostic required** (IFNDR): the compiler may stay silent, and the program has no guarantees at all.

## Dynamic initialization is ill-formed (¶2–¶3)

```cpp error
const char* g() { return "dynamic initialization"; }
constexpr const char* f(bool p) { return p ? "constant initializer" : g(); }
constinit const char* c = f(true);    // OK: evaluation only takes the true branch and doesn't call g
constinit const char* d = f(false);   // error: calls the non-constexpr g
```

This is the standard's example in paragraph 3. `f` is a constexpr function; some calls can be constant-evaluated and some can't. `constinit` checks this particular initialization.

¶2 If a variable with `constinit` has dynamic initialization, the program is ill-formed, even if the implementation would perform that initialization as static initialization.

!!! std
    If a variable declared with the `constinit` specifier has dynamic initialization, the program is ill-formed, even if the implementation would perform that initialization as a static initialization.

[[basic.start.static]] permits an implementation to perform some dynamic initialization early as static initialization. If `constinit` went by this optimization, the same code could pass on one compiler and fail on another. So the decision follows only the standard's rules.

## Differences from constexpr and const

```cpp run ok
#include <mutex>
#include <cstdio>
struct Logger {
    constexpr Logger() = default;     // constexpr constructor: can be constant-initialized
    ~Logger() { std::puts("bye"); }   // destructor is not constexpr
    int lines = 0;
};
constinit Logger logger;              // OK
constinit std::mutex global_mutex;    // OK: mutex's default constructor is constexpr
int main() {
    std::lock_guard lk(global_mutex);
    ++logger.lines;                   // OK: a constinit variable is not const
}
```

`Logger`'s destructor is not constexpr, so it is not a literal type and `constexpr Logger lg;` would be rejected; `constinit` doesn't care. `std::mutex`'s default constructor is constexpr precisely so that a global mutex can be statically initialized and therefore used safely from any dynamic initialization code. `constinit` lets the compiler confirm this for you.

| | `constexpr` variable | `constinit` variable | `const` variable |
|---|---|---|---|
| Initialization must be constant initialization | Yes | Yes | No |
| Variable is const | Yes | No, modifiable | Yes |
| Usable in constant expressions | Yes | No (unless it is also a const integral type, etc.) | Only const integral or enumeration types that are constant-initialized |
| Requires a literal type | Yes | No | No |
| Requires compile-time destruction | Yes | No | No |
| Applicable storage durations | Any | Static and thread only | Any |

An initialization that needs to allocate memory during constant evaluation is not constant initialization:

```cpp error
#include <string>
constinit std::string s2 = "a string too long for the small-string buffer of any implementation";
// error: memory allocated is not freed by the end of constant evaluation
```

A default-constructed empty string, `constinit std::string s;`, is usually well-formed, because mainstream implementations have a constexpr default constructor that doesn't allocate.

!!! tip "constinit thread_local and performance"
    When a `thread_local` variable that might have dynamic initialization is accessed from another TU, the compiler first has to call a wrapper function to make sure it has been initialized in the current thread (see the implementation notes in [[dcl.stc]]). If the declaration states `constinit` (for example `extern constinit thread_local int x;` in a header), the compiler knows there is no dynamic initialization and can access the TLS slot directly, saving a call. This is one of the rare cases where `constinit` directly affects code generation.

!!! impl "Implementation notes"
    - Clang 23 diagnoses dynamic initialization with "variable does not have a constant initializer" and points to the subexpression that caused the failure.
    - When a reachable `constinit` declaration exists but the initializing declaration lacks it, Clang only gives a `-Wmissing-constinit` warning. By paragraph 1 this is an ill-formed case that requires a diagnostic, and a warning satisfies that requirement.
    - Before C++20, Clang did the same check with the attribute `[[clang::require_constant_initialization]]`; `constinit` essentially standardizes it.

!!! pitfall "Common misconceptions"
    - constinit makes a variable a compile-time constant: it only guarantees the initial value is determined at compile time; afterwards it can be modified freely, and it can't be used in constant expressions.
    - constinit solves every static initialization order problem: it guarantees that other global variables read the correct initial value during their dynamic initialization, but it does nothing about destruction order.
    - constinit is constexpr without const: it also drops the literal-type and compile-time-destruction requirements, and it only applies to variables with static or thread storage duration.

!!! question "Question"
    Which of the following declarations are well-formed?

    ```cpp
    int a = 1;
    constinit int& r1 = a;
    constinit int* p1 = &a;
    constinit int b = a;
    constexpr int c = 2;
    constinit int d = c;
    ```

<details markdown="1">
<summary>Answer</summary>

- `r1` is well-formed: the reference binds to `a`, an object with static storage duration, and the address of `a` is a constant expression, so this is constant initialization.
- `p1` is well-formed for the same reason.
- `b` is ill-formed: reading the value of `a` requires an lvalue-to-rvalue conversion, and `a` is neither a constexpr variable nor a const integral variable, so it can't be used in a constant expression and `b` is dynamically initialized. An implementation will very likely optimize it into static initialization, but paragraph 2 says that doesn't count. Clang 23 reports "variable does not have a constant initializer".
- `d` is well-formed: `c` is a constexpr variable and can be used in constant expressions.
</details>
