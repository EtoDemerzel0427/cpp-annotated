---
title: Declaration statements
summary: "When declarations in a block are constructed and destroyed; why goto and switch cannot skip the initialization of a variable; local static variables are initialized the first time control passes through, thread-safely, retried after an exception, with recursive entry being UB."
updated: 2026-10-19
---

!!! tldr
    - Whenever control leaves the scope of an automatic variable, the variable is destroyed in reverse order of construction; whenever control passes a declaration, the variables it declares are initialized. This is the language foundation of RAII.
    - `goto` and `switch` cannot jump into a variable's scope past its initialization; only initialization that does nothing (such as `int x;`) can be skipped.
    - A local `static` variable is initialized the first time control passes through its declaration; if the initialization throws, it is retried next time; if several threads arrive at once, only one initializes and the others wait.
    - Recursively re-entering the same declaration during its initialization is undefined behavior.
    - A local `static` object is destroyed only if it was constructed.

## Declaration statements (¶1)

¶1 A **declaration statement** is a *block-declaration* ([[dcl.pre]]) written in a block: variable declarations, `using` declarations, alias declarations, `static_assert` and so on. Function definitions, namespace definitions and template declarations are not *block-declaration*s, so they cannot be written in a function body.

If a new name was already declared in an outer block, the outer declaration is hidden for the rest of this block and restored after leaving it (Note 1, [[basic.lookup.unqual]]):

```cpp run ok
int x = 1;
int main() {
    int r = x;           // the global x, r = 1
    {
        int x = 10;      // hides the global x
        r += x;          // r = 11
    }
    r += x;              // the global x again, r = 12
    return r == 12 ? 0 : 1;
}
```

Hiding begins at the point of declaration ([[basic.scope.pdecl]]), so the `x` in the initializer of `int x = x;` is already the `x` being declared, and what it reads is its own uninitialized value.

## Construction, destruction and jumps (¶2)

### Jumping back is fine, jumping past is not

```cpp run ok
#include <cstdio>
struct X {
    int n;
    X(int n) : n(n) { std::printf("X(%d) ", n); }
    ~X() { std::printf("~X(%d) ", n); }
};
int main() {
    int k = 0;
ly:
    X a = ++k;
    if (k < 3) goto ly;      // each jump back: destroy a first, then construct it again
}                            // prints: X(1) ~X(1) X(2) ~X(2) X(3) ~X(3)
```

Jumping backward to before the declaration of `a` destroys `a` first, and it is constructed again when the declaration is executed. The other direction does not work:

```cpp error
struct X { X(int); ~X(); };
void f() {
    goto lx;          // error: jumps into the scope of a, skipping its initialization
ly:
    X a = 1;
lx:
    goto ly;          // OK: a is destroyed first and constructed again after jumping to ly
}
```

If the first `goto` were allowed, `a` would never have been constructed when `lx` is reached, yet it would be destroyed on leaving the scope, and every later use of `a` would act on an object that does not exist.

### The rule

¶2 The standard unifies these cases with active variables. A block variable with automatic storage duration is [[g:active-variable|active]] from just after its *init-declarator* to the end of its scope.

Each time control transfers within a function from point P to point Q (including proceeding to the next statement, but not including function calls):

1. variables active at P and not active at Q are destroyed in reverse order of construction;
2. then, variables active at Q but not at P are initialized in declaration order;
3. if any variable in step 2 has initialization that is not vacuous, the transfer shall not be a jump.

When a declaration statement is executed, P and Q are the points immediately before and after it; when a function returns, Q is after the function body, so all local variables are destroyed. Footnote 67 adds that a transfer from the condition of a `switch` to a `case` label counts as a jump.

| Control transfer | Step 1: destroy | Step 2: initialize |
|---|---|---|
| Executing a declaration statement in sequence | nothing | the newly declared variables, that is, executing this declaration |
| Leaving a block (reaching `}`, `break`, `return`, an outward `goto`) | the constructed variables of the block | nothing |
| A backward `goto` to before some declaration | the variables passed over | nothing |
| A forward `goto` or `case` skipping some declaration | nothing | initialization is needed, but there is no initializer at the target, so only vacuous initialization is allowed |

### Vacuous initialization

[[g:vacuous-initialization|Vacuous initialization]] ([[basic.life#2]]) means a variable is default-initialized, no other initialization is performed, and, if it is of class type (or an array of class type), the default-initialization selects a trivial constructor. Such initialization does nothing anyway, so skipping it is no different from performing it.

| Declaration | Vacuous initialization? | Can it be skipped? |
|---|---|---|
| `int x;`, `int a[10];` | yes | yes |
| `int x = 0;`, `int x{};` | no | no |
| `struct P { int a; }; P p;` | yes, trivial default constructor | yes |
| `P p{};` | no, value-initialization | no |
| `std::string s;` | no, the constructor is non-trivial | no |
| `static int s = 1;` | the rule only covers automatic variables | yes |

<div class="compare" markdown="1">

```cpp ok
struct P { int a; };
void h(int k) {
  switch (k) {
  case 0:
    P p;      // vacuous initialization
    p.a = 1;
    (void)p;
    break;
  case 1:     // OK
    break;
  }
}
```

```cpp error
struct P { int a; };
void h(int k) {
  switch (k) {
  case 0:
    P p{};    // value-initialization
    (void)p;
    break;
  case 1:     // error: skips the initialization of p
    break;
  }
}
```

</div>

Variables declared in conditions and *init-statement*s are subject to the same rule:

```cpp error
int f();
void g() {
    goto L;                  // error: skips the initialization of x in the condition
    if (int x = f()) {
    L: ;
    }
}
```

Skipping `int x;` is valid, but the skipped variable has no determinate value. Since C++26, an uninitialized automatic variable holds an [[g:erroneous-value|erroneous value]] ([[basic.indet]]), and reading it is erroneous behavior {{erroneous}} rather than UB, except when the variable has the `[[indeterminate]]` attribute, in which case reading it is still UB.

!!! lawyer "Does a non-trivial destructor still count?"
    The wording from C++11 to C++17 required a skipped variable to have scalar type, or class type with a trivial default constructor and a trivial destructor, and no initializer. The current draft looks only at vacuous initialization, which concerns only the constructor. Read literally, the jump below is now well-formed: the initialization of `d` does nothing, and it is destroyed as usual on leaving the scope.

    ```cpp
    struct D { int v; ~D() {} };   // trivial default constructor, non-trivial destructor
    void f(int k) {
        switch (k) {
        case 0: D d; break;
        case 1: break;             // skips the declaration of d
        }
    }
    ```

    Clang 23 still rejects it, with a diagnostic saying the jump bypasses a variable with a non-trivial destructor, that is, it still follows the old rule.

## Initialization of local static variables (¶3)

### Initialized the first time through

¶3 Dynamic initialization of a block variable with static or thread storage duration is performed the **first time control passes through its declaration**; the variable is considered initialized once its initialization completes.

Only dynamic initialization is meant here. If the variable can be constant-initialized ([[basic.start.static]]), as with `static int n = 42;`, `static constexpr ...` or `static constinit ...`, it is initialized before the program starts, and no check is needed at run time.

If the function is never called, or control never reaches the declaration, the variable is never initialized. The lazy initialization of the Meyers singleton relies on exactly this.

### Retried when initialization throws

An initialization that exits via an exception is not complete, and it is tried again the next time control enters the declaration:

```cpp run ok
#include <cstdio>
#include <stdexcept>
int attempts = 0;
struct Res {
    Res() {
        if (++attempts < 3) throw std::runtime_error("retry");
        std::puts("constructed");
    }
};
Res& get() { static Res r; return r; }
int main() {
    for (int i = 0; i < 5; ++i) {
        try { get(); std::printf("ok at %d\n", i); break; }
        catch (const std::exception& e) { std::printf("failed: %s\n", e.what()); }
    }
    return attempts == 3 ? 0 : 1;   // fails twice, succeeds the third time
}
```

### Concurrency: initialized only once {{c++11}}

If one thread is initializing the variable and another thread enters the declaration, the latter must wait for the initialization to complete. So the initialization of local static variables is thread-safe; this guarantee was introduced in C++11 ([[N2660]]) and is often called magic statics. The singleton below needs no extra locking under multiple threads:

```cpp run ok
#include <thread>
#include <vector>
struct Config {
    int value;
    Config() : value(42) {}
};
const Config& config() {
    static const Config c;     // initialized once; concurrent calls are safe
    return c;
}
int main() {
    std::vector<std::thread> ts;
    for (int i = 0; i < 8; ++i) ts.emplace_back([] { (void)config().value; });
    for (auto& t : ts) t.join();
    return config().value == 42 ? 0 : 1;
}
```

Note 2 requires that the implementation not introduce deadlock around the initializer through its own synchronization. So an implementation cannot protect all local static variables with one global lock: otherwise A's initializer waiting for another thread to initialize B would hang. Deadlocks caused by the program's own logic are not covered by the guarantee; see Question 2.

### Recursive entry is UB

If control re-enters the declaration recursively in the same thread while the initialization is still incomplete, the behavior is undefined {{ub}} (Example 2 in the standard):

```cpp run ub
int foo(int i) {
    static int s = foo(2 * i);    // UB: the recursive call re-enters here before s is initialized
    return i + 1;
}
int main() { return foo(1); }
```

Running this program on macOS with libc++abi, it terminates with `abort`, printing a message beginning with `__cxa_guard_acquire detected recursive initialization`. libstdc++'s implementation also detects this case and throws an exception.

!!! impl "Guard variables in the Itanium C++ ABI"
    GCC and Clang generate a guard variable for each local static variable that needs dynamic initialization, with code roughly like this:

    ```text
    if (first byte of guard == 0)                    // acquire load; skip if already initialized
        if (__cxa_guard_acquire(&guard)) {           // lock and check again
            try { initialize the variable; }
            catch (...) { __cxa_guard_abort(&guard); throw; }   // retry next time
            __cxa_guard_release(&guard);             // mark done, wake waiters
            register the destructor with __cxa_atexit;
        }
    ```

    Once initialization is complete, each pass through the declaration costs only one acquire load and one comparison. `-fno-threadsafe-statics` removes the locking and is only suitable for code known to be single-threaded. MSVC has provided thread-safe initialization by default since Visual Studio 2015, and `/Zc:threadSafeInit-` turns it off.

## Destruction of local static objects (¶4)

¶4 The object associated with a local static or thread_local variable is destroyed if and only if it was constructed. For the order of destruction see [[basic.start.term]]: objects with static storage duration are destroyed in reverse order of the completion of their construction, and objects with thread storage duration are destroyed when the thread exits.

So if `get()` is never called, the `static Res r;` in it is never destroyed either. In the pseudocode above, the destructor is registered only when initialization completes, which satisfies exactly this, and the moment of registration also determines its position in the reverse-order destruction.

!!! pitfall "The order of destruction of static objects"
    If the destructor of a global object `A` calls `get()`, and the `static Res r` in `get()` completed construction after `A`, then `r` is destroyed before `A`. When `A` is destroyed, control passes through the declaration of `r`, and the behavior is undefined ([[basic.start.term#5]]). A common workaround is to make the object never destroyed:

    ```cpp ok
    struct Logger { void log(const char*) {} };
    Logger& logger() {
        static Logger& l = *new Logger;   // deliberately leaked: safe to use from any static object's destructor
        return l;
    }
    ```

## History and evolution

!!! history
    - C++98: local static variables are initialized the first time through and retried after an exception; the jump rule required skipped variables to be of POD type with no initializer. There were no threads, so there was no concurrency rule.
    - C++11: the initialization of local static variables must be thread-safe ([[N2660]]), and recursive entry is UB; the jump rule changed to require a trivial default constructor and a trivial destructor.
    - Later revisions based the jump rule on vacuous initialization and rewrote it in the current form of active variables plus P→Q control transfers.
    - C++26: uninitialized automatic variables hold erroneous values, so reading `x` after skipping `int x;` is erroneous behavior ([[basic.indet]]).

## Common misconceptions

!!! pitfall "A local static variable is initialized on every call"
    In `void f(int n) { static int cache = compute(n); }`, `cache` is initialized only with the `n` of the first call; later values of `n` have no effect.

!!! pitfall "Local static variables cost nothing"
    A dynamically initialized local static variable costs an acquire load and a comparison on every pass, and it also hinders constant propagation after inlining. Where constant initialization is possible, write `constexpr` or `constinit`.

## Questions

!!! question "Question 1"
    Is the jump below valid?
    ```cpp
    void f(bool b) {
        if (b) goto skip;
        int arr[4];
        static int s = 1;
    skip:
        (void)arr; (void)s;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Valid, and Clang accepts it too. `arr` is a default-initialized array of `int`, which is vacuous initialization and can be skipped. `s` has static storage duration, and ¶2 only covers automatic variables; besides, `s = 1` is constant initialization, completed before the program starts. `(void)arr` reads no element, so there is no erroneous behavior either.
</details>

!!! question "Question 2"
    The initializer of a local static variable starts a thread that calls the same function, and the initializer then `join`s it. What happens?

<details markdown="1">
<summary>Answer</summary>

Deadlock. The new thread enters the declaration, finds the variable being initialized, and by ¶3 must wait; the original thread's initializer is waiting for the new thread to finish. This deadlock comes from the program's logic, and Note 2 only requires the implementation not to introduce deadlock through its own synchronization, so the standard guarantees no particular outcome. Nor is this recursive entry, since the declaration is re-entered by a different thread.
</details>
