---
title: Exception handling preamble
summary: "The syntax of try blocks, handlers and function-try-blocks; you cannot jump into a try block or handler but can jump out, in which case local variables are destroyed in the context of their declarations; a function-try-block can catch exceptions thrown while a constructor initializes its members."
updated: 2026-10-19
---

!!! tldr
    - A try block's handlers are invoked only when code executed in the try block (including functions called from there) throws. A handler cannot be called directly, nor jumped into.
    - The braced parts of a try block and its handlers are control-flow-limited statements: they cannot be entered from outside by `goto` or `case`, but `goto`, `break`, `return` and `continue` can jump out of them.
    - When jumping out, local variables are destroyed at the level where they are declared; an exception thrown by their destructor is handled by the handlers around that declaration.
    - A function-try-block wraps the whole function body, member initializer list included, in a try block, so it can catch exceptions thrown while a constructor initializes its members.
    - A handler of a function-try-block of a constructor or destructor rethrows automatically when it reaches its end; the exception cannot be swallowed.

## Syntax (¶1)

```cpp run title="handler-syntax.cpp" ok
#include <cstdio>
#include <stdexcept>

int main() {
    try {
        throw std::runtime_error("boom");
    } catch ([[maybe_unused]] const std::logic_error& e) {   // named parameter; the attribute appertains to e
        std::puts("logic_error");
    } catch (const std::exception&) {                         // unnamed parameter
        std::puts("exception");
    } catch (...) {                                           // matches any exception
        std::puts("other");
    }
}
```

¶1 `try` is followed by a compound statement and then one or more **handlers** (`catch` clauses). The parentheses of each handler contain an *exception-declaration*, shaped like a function parameter declaration: it can have a name or not, or be `...`. Both `try` and `catch` must be followed by braces; `try f();` is not valid.

The first sentence of ¶1 says what exception handling is: a transfer of control and information from a point in the execution of a thread to a handler associated with a point previously passed by the execution. Two things follow:

- A handler can only belong to a try block that has been entered and not yet exited; an exception never jumps into code that has not been reached yet.
- The search happens only within the same thread ([[except.handle#6]]). Exceptions do not propagate across threads by themselves; that takes `std::exception_ptr` ([[propagation]]) or `std::future`.

¶2 A *try-block* is a statement ([[stmt.pre]]) and can appear wherever a statement can be written. A function-try-block is not a statement but a form of function body (see below). When this chapter says try block, it means both.

## No jumping into a try block or handler (¶3)

<div class="compare" markdown="1">

```cpp title="goto-into-try.cpp" error
void f(int c) {
  goto l1;      // error: jumps into a try block
  try {
    l1: ;
  } catch (...) {
    goto l1;    // error: jumps back from a handler
  }
  switch (c) {
    try {
      case 1: ; // error: the case is in the try block,
    } catch (...) { }  //  the switch is outside
  }
}
```

```cpp title="goto-inside-try.cpp" ok
void f() {
  try {
    goto l1;    // OK: the label and the goto
    l1: ;       //     are in the same try block
  } catch (...) {
    goto l2;    // OK: in the same handler
    l2: ;
  }
}
```

</div>

¶3 The compound statement of a try block and the compound statements of handlers are **control-flow-limited statements** ([[stmt.label#3]]). This means labels in them can only be used by `goto`s inside, and `case` and `default` labels in them can only belong to a `switch` inside. So all three jumps on the left are ill-formed.

Jumping in is forbidden because entering a try block has run-time meaning: the search for a handler depends on which try blocks have been entered and not yet exited ([[except.throw#2]]). Landing in the middle of the block without passing the `try` keyword would leave that state undefined. Jumping into a handler makes even less sense: there is no exception being handled there, so the handler's parameter and `throw;` would have nothing to refer to.

Clang's note for this kind of error is jump bypasses initialization of try block, reusing the machinery that checks for skipped declarations with initialization ([[stmt.dcl]]); the standard's basis is control-flow-limited statements.

## Jumping out of a try block (¶3)

The second half of ¶3 allows jumps in the opposite direction: `goto`, `break`, `return` and `continue` can all transfer control out of a try block or handler. Each variable declared in the try block is then destroyed in the context that directly contains its declaration.

This sentence decides who handles an exception thrown by a destructor: the try block around the variable's declaration, not the try block at the `goto`'s target.

```cpp run title="goto-out.cpp" ok
#include <cstdio>

struct T {
    const char* n;
    bool throws;
    ~T() noexcept(false) {
        std::printf("~%s\n", n);
        if (throws) { throws = false; throw n; }
    }
};

int main() {
    int round = 0;
lab:
    try {
        T t1{"t1", false};
        try {
            T t2{"t2", round == 0};    // first round: t2 throws when destroyed
            if (round++ == 0)
                goto lab;              // destroys t2 first, then t1
        } catch (const char* who) {
            std::printf("handler 2 caught %s\n", who);
        }
    } catch (const char* who) {
        std::printf("handler 1 caught %s\n", who);
    }
}
```

Output:

```text
~t2
handler 2 caught t2
~t1
```

`goto lab` first triggers the destruction of `t2`. `t2` is declared in the inner try block, so the exception thrown by its destructor is caught by handler 2. The exception interrupts the `goto`, and control continues after handler 2: the inner try block ends, the outer compound statement ends, `t1` is destroyed normally, and the program never returns to `lab`.

## function-try-block (¶4)

A constructor's member initialization happens before the `{` of the function body, so an ordinary try block in the body cannot cover it. A function-try-block puts `try` before the initializer list, which is exactly what solves this:

```cpp run title="ctor-ftb.cpp" ok
#include <cstdio>

struct Member {
    explicit Member(int x) { if (x < 0) throw x; }
};

struct C {
    Member m;
    explicit C(int x)
    try : m(x) {                          // the initializer list is within the try too
        std::puts("ctor body");
    } catch (int e) {
        std::printf("ctor handler saw %d\n", e);
    }                                     // reaching the end: automatic rethrow
};

int main() {
    try {
        C c(-1);
    } catch (int e) {
        std::printf("main caught %d again\n", e);
    }
}
```

Output:

```text
ctor handler saw -1
main caught -1 again
```

¶4 The handlers of a function-try-block can catch three kinds of exceptions: those thrown during execution of the function body; for a constructor, those thrown while initializing bases and members; for a destructor, those thrown while destroying bases and members.

When a constructor fails, the object has not been constructed, and the caller must learn of this. So [[except.handle]] places three restrictions on function-try-blocks of constructors and destructors:

| Rule | Source |
|---|---|
| When a handler reaches its end, the currently handled exception is rethrown automatically | [[except.handle#14]] |
| A `return` statement in a handler of a constructor makes the program ill-formed | [[except.handle#13]] |
| Referring to a non-static member or base of the object in a handler is undefined behavior; they have already been destroyed | [[except.handle#11]] |

```cpp title="ctor-handler-return.cpp" error
struct M { M(int); };
struct C {
    M m;
    C(int x) try : m(x) { } catch (...) {
        return;     // error: no return in a handler of a constructor's function-try-block
    }
};
```

So a handler can only do a few things: log, translate the exception into another exception and throw it, and clean up resources that are not members (things passed in through parameters, for instance). Ending the handler with `throw OtherError{};` or calling `std::exit` is allowed, since neither reaches the end of the handler.

A destructor's handler also rethrows on reaching its end, but a destructor's handler may contain `return;`, which swallows the exception. Destructors are `noexcept` by default, though ([[except.spec#8]]), so this form is rare:

```cpp run title="dtor-ftb.cpp" ok
#include <cstdio>

struct Bad { ~Bad() noexcept(false) { throw 1; } };

struct H {
    Bad b;
    ~H() noexcept(false)
    try {
    } catch (int) {
        std::puts("dtor handler");   // thrown when member b is destroyed, caught here
    }                                // reaching the end: automatic rethrow
};

int main() {
    try { H h; } catch (int) { std::puts("rethrown to main"); }
}
```

For an ordinary function, a function-try-block is much like wrapping the whole function body in a try block: a handler reaching its end is like the function body reaching its end ([[except.handle#14]]). The difference is that the handler can still access the function parameters. A function-try-block on `main` does not catch exceptions thrown during the construction and destruction of objects with static storage duration ([[except.handle#12]]).

## Common misconceptions

!!! pitfall "Thinking a function-try-block can rescue the construction"
    By the time the handler is entered, all subobjects already constructed have been destroyed ([[except.ctor#3]]), and the end of the handler rethrows automatically, so repairing the members in the handler and letting the object continue construction is impossible. To fall back to a default value on failure, handle it in the member's initializer expression, for example by calling a factory function that catches exceptions internally.

!!! pitfall "Reading members in a constructor's handler"
    ```cpp
    struct S {
        std::string name;
        Res r;
        S() try : name("x"), r(open()) {} catch (...) {
            log(name);    // UB: name has already been destroyed
        }
    };
    ```
    Clang gives only a `-Wexceptions` warning for this. Information the handler needs should come from the constructor's parameters or from static data.

## Questions

!!! question "Question"
    Is the code below well-formed? What if the whole `switch` is put inside the try block?

    ```cpp
    void f(int c) {
        switch (c) {
            case 0:
                try { case 1: break; } catch (...) { }
        }
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It is ill-formed. `case 1:` is in the compound statement of the try block, which is a control-flow-limited statement, so a `case` in it must belong to a `switch` inside it ([[stmt.label#3]]), but the `switch` here is outside the try block. `case 0:` is outside the try block and is fine.

Changed to `try { switch (c) { case 1: break; } } catch (...) {}`, both the `switch` and the `case` are inside the try block, and the program is well-formed.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 The optional attribute-specifier-seq in an *exception-declaration* appertains to the parameter of the catch clause, as in `catch ([[maybe_unused]] const E& e)`.

¶2 Note 1: within this chapter, try block refers to both *try-block* and *function-try-block*.

¶3 Earlier standards phrased this rule as a `goto` or `switch` statement shall not be used to transfer control into a try block or into a handler. It is now expressed in terms of control-flow-limited statements, defined uniformly in [[stmt.label]], with the same effect; the same concept is used for the branches of `if constexpr` and `if consteval`.

¶5 In this chapter, before and after refer to the sequenced-before relation ([[intro.execution]]), that is, ordering within a single thread. Exception handling itself implies no thread synchronization (Note 2 in [[except.throw#4]]).

</details>
