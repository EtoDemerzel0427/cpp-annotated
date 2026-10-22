---
title: Undefined behavior in [dcl]
summary: "The nine kinds of undefined behavior stated explicitly in Clause 9: modifying const objects, bypassing volatile access, binding references to functions or objects of the wrong type, using a reference before its initialization, resuming or destroying a coroutine that is not suspended, an assume assumption that does not hold, and a noreturn function that returns."
updated: 2026-10-19
---

!!! tldr
    - Modifying a const object is undefined behavior, where a const object means one that was const when defined; casting away const with `const_cast` from a pointer to a non-const object and writing through it is valid.
    - Type correctness is required already at reference binding: binding an `int&` to a `float` object is undefined behavior even if you never read or write through it.
    - Only a suspended coroutine can be `resume`d or `destroy`ed; destroying a coroutine while it is running makes it continue executing on a freed coroutine frame.
    - An `[[assume]]` condition that does not hold and a `[[noreturn]]` function that returns are both runtime-undefined behavior: at run time they are the same as ordinary UB, and in constant evaluation it is up to the implementation whether to treat them as making the expression non-constant.

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.5 subclause corresponds to Clause 9 [dcl], with nine entries.

All run results below come from Clang 23 (arm64 macOS), compiled by default with `-O0 -g -fsanitize=address,undefined`, i.e. with both ASan (which checks memory accesses) and UBSan (which checks some undefined behavior) on. Constant evaluation means putting the same operation into the initializer of a `constexpr` variable; per [[expr.const.core]], the compiler must reject core language undefined behavior there.

## cv-qualifiers

### F.5.1 Modifying a const object during its lifetime {#dcl.type.cv.modify.const.obj}

`[ub:dcl.type.cv.modify.const.obj]` · main text [[dcl.type.cv#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

const int g = 3;

int main() {
  int i = 2;
  const int* cip = &i;
  *const_cast<int*>(cip) = 4;   // OK: i itself is not a const object

  const int* ciq = new const int(3);
  *const_cast<int*>(ciq) = 4;   // UB: modifying a const object (dynamically allocated ones count too)
  delete ciq;

  *const_cast<int*>(&g) = 4;    // UB: modifying a const object
  std::printf("%d\n", g);
}
```

This rule is about const objects themselves, not about objects accessed through a const path. `i` was not const when defined, so casting the const away from `cip` and writing is perfectly valid. Only when the object is defined const, or created with `new const T`, is writing undefined behavior. `mutable` members of a class are not subject to this restriction.

At run time there is no report for the heap case, and the write succeeds. For the global `g`, ASan reports `BUS on unknown address`: `g` was placed in a read-only segment and the write causes a bus error. In constant evaluation, modifying a const object is rejected with `modification of object of const-qualified type 'const int' is not allowed in a constant expression`.

### F.5.2 Accessing an object defined volatile through a non-volatile glvalue {#dcl.type.cv.access.volatile}

`[ub:dcl.type.cv.access.volatile]` · main text [[dcl.type.cv#5]]

```cpp ub
#include <cstdio>

volatile int x = 0;

void f() {
  int& y = const_cast<int&>(x);
  std::printf("%d\n", y);   // UB: accessing a volatile object through a non-volatile glvalue
}
```

Every read and write of a volatile object must be performed exactly as written; the compiler may not merge or remove them (see observable behavior in [[intro.abstract]]). If an object defined volatile is accessed through a reference or pointer without volatile qualification, the compiler optimizes those accesses as ordinary ones and the volatile guarantee is lost. So the standard makes such access undefined behavior.

## References

### F.5.3 A function reference bound to a function of incompatible type {#dcl.ref.incompatible.function}

`[ub:dcl.ref.incompatible.function]` · main text [[dcl.ref#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

void f(float x) { std::printf("%f\n", x); }
void (&g)(int) = reinterpret_cast<void (&)(int)>(f);   // UB: already at binding

int main() { g(1); }
```

The type of a function reference must be call-compatible ([[g:call-compatible]]) with the definition of the function it is bound to, roughly: the same type, or differing only by `noexcept`. This is the reference version of [[ub.expr#expr.call.different.type|F.3.11]], but the undefined behavior happens earlier: the binding itself is undefined behavior, without waiting for the call.

At compile time Clang gives a `-Wcast-function-type-mismatch` warning. At run time UBSan's `function` check reports `call to function f(float) through pointer to incorrect function type 'void (*)(int)'` at the call, and the program then prints a floating-point number unrelated to 1. Tools can only find the problem at the call; the standard's point of judgment is the binding.

### F.5.4 An object reference bound to an object that cannot be accessed through that type {#dcl.ref.incompatible.type}

`[ub:dcl.ref.incompatible.type]` · main text [[dcl.ref#6]]

```cpp ub
float g;
int& i = reinterpret_cast<int&>(g);   // UB: a float object cannot be accessed through an int glvalue
```

The referenced object must be accessible through the reference's type ([[g:type-accessible]]), which is the rule usually called strict aliasing (see [[ub.expr#expr.basic.lvalue.strict.aliasing.violation|F.3.2]]). Again the point of judgment is the binding: even if `i` is never used for reading or writing afterwards, the code above is already undefined behavior. A note in the main text adds that the referenced object may be outside its lifetime; that case is governed by [[basic.life]].

Running it reports nothing.

### F.5.5 Evaluating a reference before its initialization {#dcl.ref.uninitialized.reference}

`[ub:dcl.ref.uninitialized.reference]` · main text [[dcl.ref#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int& g();
extern int& ir3;
int i2 = ir3;      // UB: ir3 is not yet initialized (its initialization comes later)
int& ir3 = g();
int& g() { static int v = 17; return v; }

int main() { std::printf("%d\n", i2); }
```

Evaluation of a reference must happen after its initialization (happens after, see [[intro.races]]). The most common way to violate this is the dynamic initialization order of global variables: within one translation unit, dynamic initialization proceeds in order of definition, and when `i2` is initialized, `ir3` is not yet bound.

At run time ASan reports `SEGV on unknown address 0x000000000000`. A reference is a pointer in the implementation, and static storage is zero-initialized before dynamic initialization, so what is read is a null pointer.

!!! lawyer "The annex's original example actually has no UB"
    The annex writes `int& ir1 = i3;`, where `i3` is a global `int`. That initializer is a constant expression (the address of an object with static storage duration), so `ir1` is constant-initialized, which is static initialization. Per [[basic.start.static]], static initialization completes before any dynamic initialization, so `ir1` is long bound when `int i2 = ir1;` runs. Running the annex's original example on Clang 23 prints `17`. The example in the main text [[dcl.ref#6]] uses `int& ir3 = g();`, which is dynamic initialization and actually demonstrates the rule; the example above is rewritten after the main text.

## Coroutines

The next two entries both require the coroutine to be suspended. A coroutine is suspended when it has stopped at a `co_await` or `co_yield`, or at the initial or final suspend point; it is not suspended while it is executing its body.

### F.5.6 Calling resume on a coroutine that is not suspended {#dcl.fct.def.coroutine.resume.not.suspended}

`[ub:dcl.fct.def.coroutine.resume.not.suspended]` · main text [[dcl.fct.def.coroutine#8]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct gen {
  struct promise_type {
    int val = 0;
    gen get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
    std::suspend_always yield_value(int v) noexcept { val = v; return {}; }
  };
  std::coroutine_handle<promise_type> h;
  ~gen() { h.destroy(); }
  bool next() { h.resume(); return !h.done(); }
};

gen f(int n) { for (int i = 0; i < n; ++i) co_yield i; }

int main() {
  gen g = f(3);
  int sum = 0;
  while (g.next()) sum += g.h.promise().val;
  g.next();   // UB: the coroutine has stopped at its final suspend point, done() is true
  return sum;
}
```

This rewrites the annex's example (the original omits `std::` on `suspend_always` and `coroutine_handle`). When the loop ends, the coroutine has finished its body and stopped at the final suspend point; calling `resume()` again is undefined behavior.

Strictly speaking, a coroutine stopped at its final suspend point is also suspended, so this example falls under the library's rule: [[coroutine.handle.resumption]] makes it a precondition of `resume()` that the coroutine is suspended and not at its final suspend point. The core language entry is about a different case: resuming a coroutine while it is running. Both cases are undefined behavior.

At run time ASan reports `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`. When a Clang coroutine frame reaches the final suspend point, its resume function pointer is set to null, so resuming again jumps to address 0.

### F.5.7 Calling destroy on a coroutine that is not suspended {#dcl.fct.def.coroutine.destroy.not.suspended}

`[ub:dcl.fct.def.coroutine.destroy.not.suspended]` · main text [[dcl.fct.def.coroutine#11]]

`destroy()` destroys the coroutine state and frees the coroutine frame. If the coroutine is executing at that moment, for example if it obtains its own handle inside its body and destroys itself, the execution that follows happens on a freed frame.

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct task {
  struct promise_type {
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() {}
  };
  std::coroutine_handle<promise_type> h;
};

std::coroutine_handle<> self;

struct grab {
  bool await_ready() { return false; }
  // returning false: grab the handle but do not suspend
  bool await_suspend(std::coroutine_handle<> h) { self = h; return false; }
  void await_resume() {}
};

task f() {
  co_await grab{};   // obtain its own handle; the coroutine keeps running
  self.destroy();    // UB: the coroutine is executing, not suspended
}

int main() { f(); }
```

At run time ASan reports `heap-use-after-free`: `destroy()` freed the coroutine frame, and the coroutine then continued executing on the frame.

The annex's example calls `destroy()` in `current_value()`, but at that time the coroutine is stopped at `co_yield` and is in fact suspended. That example's real problems are accessing the promise after destruction and calling `destroy()` a second time in the destructor, so a different example is used here.

## Attributes

The last two entries are written in the main text as **runtime-undefined behavior** ([[defns.undefined.runtime]]): at run time it is the same as ordinary undefined behavior; in constant evaluation, whether it makes an expression non-constant is implementation-defined ([[expr.const.core#3]]), and it has no other effect.

### F.5.8 An assumption does not hold where it appears {#dcl.attr.assume.false}

`[ub:dcl.attr.assume.false]` · main text [[dcl.attr.assume#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int g(int x) {
  [[assume(x >= 0)]];   // lets the compiler compile x / 32 as a single right shift
  return x / 32;
}

int main(int argc, char**) {
  std::printf("%d\n", g(-10 * argc));   // UB: the assumption does not hold
}
```

The expression in `[[assume(expr)]]` (C++23) is not evaluated; it only tells the compiler that `expr` is certainly true at this point. If it is not actually true, the evaluation of the assumption is runtime-undefined behavior. A wrong assumption makes the optimizer generate wrong code, so use it only when you are really sure.

At run time UBSan reports `assumption is violated during execution`. In constant evaluation, Clang rejects `g(-10)` with `assumption evaluated to false`. This is runtime-undefined behavior and whether to reject is implementation-defined; Clang chooses to reject.

### F.5.9 A function declared `[[noreturn]]` returns {#dcl.attr.noreturn.eventually.returns}

`[ub:dcl.attr.noreturn.eventually.returns]` · main text [[dcl.attr.noreturn#2]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

[[noreturn]] void f(int i) {
  if (i > 0)
    throw "positive";
}   // returns when i <= 0

int main(int argc, char**) {
  f(argc - 1);   // UB: f(0) returned
  std::puts("returned");
}
```

A `[[noreturn]]` function may be left by throwing an exception, but may not return normally. This too is runtime-undefined behavior.

At compile time Clang warns `function declared 'noreturn' should not return [-Winvalid-noreturn]`, the warning [[dcl.attr.noreturn#3]] recommends implementations give. At run time UBSan reports `execution reached an unreachable program point`. Compiled with `-O2`, the `puts` is removed entirely and the process terminates abnormally.

In constant evaluation, Clang accepts a call to a `[[noreturn]] constexpr` function that returns, and does not treat the expression as non-constant because of it. This differs from its handling of `[[assume]]`, but both choices conform to the standard; that is exactly what implementation-defined means.
