---
title: Undefined behavior in [except]
summary: Referring to a non-static member or base of the object in the handler of a constructor's or destructor's function-try-block is undefined behavior, because by then they have been destroyed or were never constructed.
updated: 2026-10-19
---

!!! tldr
    - A constructor's function-try-block can catch exceptions thrown during member initialization and base construction, but by the time the handler is entered, the members and bases already constructed have been destroyed.
    - So referring to any non-static member or base of the object in this handler is undefined behavior; the same goes for a destructor's function-try-block.
    - The only things the handler can safely use are the function's parameters, static members and global state.
    - When the handler reaches its end, the exception is rethrown automatically and the object's construction still fails; writing `return` in a constructor's handler is ill-formed.

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.8 subclause corresponds to Clause 14 [except] and has a single entry.

A **function-try-block** wraps the whole function body (and, for a constructor, the member initializer list too) in a `try`: `A() try : x(...) { ... } catch (...) { ... }`. It is the only way to catch exceptions thrown while constructing members or bases.

### F.8.1 Referring to members or bases in the handler of a function-try-block {#except.handle.handler.ctor.dtor}

`[ub:except.handle.handler.ctor.dtor]` · main text [[except.handle#11]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

struct A {
  A() try : x(0 ? 1 : throw 1) {
  } catch (int) {
    std::printf("y: %d\n", y);   // UB: referring to the non-static member y in the handler
  }   // reaching the end of the handler: the exception is rethrown automatically
  int x;
  int y = 42;
};

int main() {
  try { A a; } catch (int) {}
}
```

The initializer of `x` throws, and control passes to the handler. Per [[except.ctor]], the subobjects already fully constructed have been destroyed by then, and those not yet constructed, such as `y` here, never existed. So reading `y` in the handler reads no object at all. A destructor's function-try-block is the same: when the handler is entered, the members and bases have already been destroyed.

At compile time Clang 23 warns `cannot refer to a non-static member from the handler of a constructor function try block [-Wexceptions]`. At run time neither ASan nor UBSan reports anything, and the program prints `y: 0`: the initializer `= 42` of `y` never ran, and the 0 is just whatever happened to be in that stack memory.

What such a handler is good for is logging, or rethrowing the exception as a different type. All it can use are the constructor's parameters, static members and global state.

### Two related rules

The following two rules often come up together with this UB, but they are not UB.

[[except.handle#14]]: when control reaches the end of the handler of a constructor's or destructor's function-try-block, the exception being handled is rethrown automatically. The handler cannot swallow the exception to make construction succeed; the object simply was not constructed. The `catch (int)` in `main` in the example above catches this rethrow.

[[except.handle#13]]: a `return` statement in the handler of a constructor's function-try-block makes the program ill-formed, and the compiler must diagnose it.

```cpp error
struct A {
  int x;
  A() try : x(0) {
  } catch (...) {
    return;   // error: no return in a constructor's handler
  }
};
```

Clang 23 reports `return in the catch of a function try block of a constructor is illegal`.
