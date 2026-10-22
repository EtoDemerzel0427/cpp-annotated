---
title: Undefined behavior in [stmt]
summary: "The three kinds of undefined behavior stated explicitly in Clause 8: a non-void function reaching its end without return, a coroutine reaching the end of its body without return_void, and a block-scope static variable being re-entered recursively during its initialization."
updated: 2026-10-19
---

!!! tldr
    - An ordinary function whose return type is not `void` reaching its end without meeting a `return` is undefined behavior, whether or not the caller uses the return value; `main` is the exception.
    - The compiler treats that path as unreachable and at `-O2` may simply delete the corresponding branch, so do not ignore `-Wreturn-type` warnings.
    - A coroutine reaching the end of its body is equivalent to `co_return;`, provided the promise type has `return_void`; if it has only `return_value`, it is undefined behavior.
    - A block-scope static variable whose initialization recursively re-enters the same declaration is undefined behavior; in our tests the runtime library detects it and aborts the program, while other implementations may deadlock.

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.4 subclause corresponds to Clause 8 [stmt]: three entries, all about control flow reaching a place it should not.

All run results below come from Clang 23 (arm64 macOS), with the compiler options shown on each example.

### F.4.1 A non-void function reaches its end {#stmt.return.flow.off}

`[ub:stmt.return.flow.off]` · main text [[stmt.return#4]]

```cpp run ub flags="-std=c++2c -O2" cc=clang_trunk
#include <cstdio>

int f(int x) {
  if (x)
    return 1;
}   // UB when x == 0

int main(int argc, char**) {
  std::printf("%d\n", f(argc - 1));   // the argument is 0 when run without arguments
}
```

When a constructor, a destructor, or an ordinary function returning cv `void` reaches its end, it is equivalent to `return;`. For any other function, reaching the end is undefined behavior, except for `main` (equivalent to returning 0) and coroutines (see the next entry).

This differs from C. C counts it as undefined behavior only if the caller uses the return value; in C++ reaching the end is undefined behavior regardless of whether the return value is used. So the compiler may conclude that the path is never executed.

At compile time Clang warns `non-void function does not return a value in all control paths [-Wreturn-type]`. Compiled with `-O2` and run without arguments, the program prints `1`: Clang concludes the `x == 0` path never happens and optimizes `f` into an unconditional return of 1.

Compiled with `-O0 -fsanitize=undefined`, UBSan reports `execution reached the end of a value-returning function without returning a value` and terminates the program. Declaring `f` `constexpr` and calling `f(0)` in constant evaluation, the compiler rejects it with `control reached end of constexpr function`.

### F.4.2 A coroutine reaches the end of its body and the promise has no return_void {#stmt.return.coroutine.flow.off}

`[ub:stmt.return.coroutine.flow.off]` · main text [[stmt.return.coroutine#3]]

A coroutine's return operation is a call on the promise object (the object in the coroutine frame that holds the result and state, see [[dcl.fct.def.coroutine]]): `co_return;` calls `p.return_void()`, and `co_return e;` calls `p.return_value(e)`. A promise type can have only one of these two functions.

If overload resolution for `p.return_void()` succeeds, a coroutine reaching the end of its body is equivalent to `co_return;`. Otherwise, reaching the end is undefined behavior. So a value-returning coroutine that forgets to write `co_return e;` falls under this entry.

```cpp run ub
#include <coroutine>
#include <exception>

struct task {
  struct promise_type {
    const char* s = nullptr;
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void unhandled_exception() { std::terminate(); }
    void return_value(const char* v) { s = v; }   // only return_value
  };
  std::coroutine_handle<promise_type> h;
  ~task() { h.destroy(); }
};

task foo() {
  co_await std::suspend_always{};
}   // UB: reaches the end of the coroutine body, and p.return_void() does not exist

int main() {
  task t = foo();
  while (!t.h.done()) t.h.resume();
  return t.h.promise().s != nullptr;
}
```

At compile time Clang warns `non-void coroutine does not return a value [-Wreturn-type]`. At run time neither ASan nor UBSan reports anything, and `s` keeps its default null pointer. The annex's original example gives the `string_` member no default value, so printing it at the end reads an uninitialized pointer, which hides the problem even better.

### F.4.3 The initialization of a block-scope static variable is re-entered recursively {#stmt.dcl.local.static.init.recursive}

`[ub:stmt.dcl.local.static.init.recursive]` · main text [[stmt.dcl#3]]

A block-scope static variable is initialized the first time control passes through its declaration. If another thread enters the declaration while initialization is in progress, it must wait for the initialization to complete; this is the thread-safety guarantee for the initialization of function-local statics.

If the same thread recursively re-enters the declaration during initialization, the standard cannot give sensible semantics: waiting would deadlock, and not waiting would read a variable that has not finished initializing. So this case is undefined behavior.

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int foo(int i) {
  static int s = foo(2 * i);   // UB: re-entering the same declaration recursively during initialization
  return i + 1;
}

int main() { std::printf("%d\n", foo(1)); }
```

At compile time Clang gives a `-Winfinite-recursion` warning. At run time, libc++abi's guard variable (the flag the compiler uses to record whether a static variable has been initialized) detects the recursive initialization, prints `libc++abi: __cxa_guard_acquire detected recursive initialization: do you have a function-local static variable whose initialization depends on that function?` and aborts the program. This is an extra check provided by the runtime library, not required by the standard; on other implementations the same code may deadlock.
