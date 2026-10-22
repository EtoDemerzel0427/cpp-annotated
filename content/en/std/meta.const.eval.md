---
title: Constant evaluation context
summary: "is_constant_evaluated() tells whether the current call is manifestly constant-evaluated; C++26's is_within_lifetime(p) tells at compile time whether the object a pointer points to is within its lifetime."
updated: 2026-10-19
---

!!! tldr
    - `std::is_constant_evaluated()` is equivalent to a boolean version of `if consteval`: it returns `true` when the call is manifestly constant-evaluated.
    - The result depends on the context of the call, not on the function itself: the same call may give `true` when initializing a static variable and `false` when initializing a local variable.
    - Do not write `if constexpr (std::is_constant_evaluated())`; it is always true. Since C++23, use `if consteval` directly.
    - C++26's `std::is_within_lifetime(p)` is a `consteval` function that tells whether the object `p` points to is within its lifetime, which lets you tell at compile time which member of a union is active.
    - `is_within_lifetime` can only ask about objects usable in constant expressions, or objects created during the current constant evaluation.

A `constexpr` function can run at compile time or at run time. Some operations can only be done on one side: at compile time you cannot call `memset`, read an inactive union member, or use inline assembly, while at run time you would like to use these faster forms. The two functions in [meta.const.eval] let code know which side it is on.

## `is_constant_evaluated`

```cpp
constexpr bool is_constant_evaluated() noexcept;
```

¶1 specifies that its effect is equivalent to

```cpp
if consteval {
  return true;
} else {
  return false;
}
```

That is, if this call is [[g:manifestly-constant-evaluated|manifestly constant-evaluated]], the result is `true`. The manifestly constant-evaluated cases are listed in [[expr.const]]; they include constant expressions (the condition of `static_assert`, array bounds, template arguments, initializers of `constexpr` variables), the condition of `if constexpr`, calls to `consteval` functions, and the attempt at constant initialization when initializing variables with static storage duration and `const` integral variables.

```cpp run title="is-constant-evaluated.cpp" ok
#include <cstdio>
#include <cstring>
#include <type_traits>

constexpr void zero(unsigned char* p, int n) {
  if (std::is_constant_evaluated()) {
    for (int k = 0; k < n; ++k) p[k] = 0;
  } else {
    std::memset(p, 0, n);  // not a core constant expression
  }
}

constexpr int f() {
  unsigned char b[4] = {1, 2, 3, 4};
  zero(b, 4);
  return b[0] + b[3];
}
static_assert(f() == 0);  // the loop is taken at compile time

constexpr int where() { return std::is_constant_evaluated(); }

int main() {
  const int a = where();  // constant initialization attempted: 1
  int b = where();        // run-time call: 0
  std::printf("%d %d %d\n", f(), a, b);  // 0 1 0
}
```

`zero` is adapted from the standard's Example 1 (paragraph 2): it clears with a loop at compile time and calls `memset` at run time. The contrast between `a` and `b` shows that the result of the same function call depends on where the call appears. `a` is a `const int`, so its initializer is first tried as a constant expression, and that evaluation is manifestly constant-evaluated; `b`'s initialization is just an ordinary run-time call.

!!! history
    When C++20 introduced this function with [[P0595R2]], it was specified to return `true` during manifestly constant-evaluated evaluation. After C++23 added `if consteval` ([[stmt.if]]), the specification was rewritten as the equivalent form above, with no change in meaning.

### Do not put it in `if constexpr`

The comment in the example of ¶2 specifically says that the `if` there should not be written as `if constexpr`. The condition of `if constexpr` is itself manifestly constant-evaluated, so `is_constant_evaluated()` always returns `true` there, and the run-time branch is discarded entirely:

```cpp run title="if-constexpr-trap.cpp"
#include <type_traits>

constexpr int g() {
  if constexpr (std::is_constant_evaluated())  // always true
    return 1;
  else
    return 2;
}

int main() { return g(); }  // a run-time call also returns 1
```

Clang gives a `-Wconstant-evaluated` warning for this, pointing out that `std::is_constant_evaluated` always evaluates to `true` in a manifestly constant-evaluated expression. The code is well-formed, just logically wrong, so it carries no verdict.

Since C++23, write `if consteval { … } else { … }` directly, which cannot make this mistake. `if consteval` has another advantage: its first branch can call `consteval` functions, which the branches of `if (std::is_constant_evaluated())` cannot.

!!! impl "libc++"
    libc++'s implementation is a single line: `return __builtin_is_constant_evaluated();`.

## `is_within_lifetime` {{c++26}}

```cpp
template<class U = void, class T>
  consteval bool is_within_lifetime(const T* p) noexcept;
```

This function was introduced by [[P2641R4]]. It is a `consteval` function, i.e. an [[g:immediate-function|immediate function]], and can only be called during constant evaluation.

### Motivation: telling a union's active member at compile time

Reading an inactive member of a union during constant evaluation is not a constant expression ([[expr.const]]), and the compiler rejects it. The following example, from paragraph 6, uses a union of a `bool` and a `char` to implement an optional `bool` that occupies a single byte:

```cpp run title="opt-bool.cpp" ok
#include <type_traits>

struct OptBool {
  union { bool b; char c; };

  // assumes sizeof(bool) == sizeof(char),
  // and that the value representations of true and false both differ from 2
  constexpr OptBool() : c(2) {}
  constexpr OptBool(bool b) : b(b) {}

  constexpr auto has_value() const -> bool {
    if consteval {
      return std::is_within_lifetime(&b);  // compile time: cannot read c
    } else {
      return c != 2;  // run time: read c
    }
  }

  constexpr auto operator*() const -> const bool& { return b; }
};

constexpr OptBool disengaged;
constexpr OptBool engaged(true);
static_assert(!disengaged.has_value());
static_assert(engaged.has_value());
static_assert(*engaged);

int main() {
  OptBool o;
  return o.has_value();
}
```

At compile time `c` cannot be read to tell whether there is a value, so instead it asks whether `b` is within its lifetime, i.e. whether `b` is the active member. The run-time branch reads `c`, which, when the active member is `b`, reads an inactive member. The comment in the example lists the implementation properties it depends on; ordinary code should not imitate this, but `is_within_lifetime` at least guarantees that the compile-time path is strictly valid.

### Return value and restrictions

¶3: `static_cast<const volatile U*>(p)` must be well-formed (*Mandates*).

¶4: returns `true` if `p` points to an object that is within its lifetime ([[basic.life]]) and `static_cast<const volatile U*>(p)` is a constant subexpression; otherwise returns `false`.

It asks only about lifetime, not about whether the value is determined. An object default-initialized with `new int` has an indeterminate value, but is already within its lifetime:

```cpp run title="within-lifetime-indeterminate.cpp" ok
#include <type_traits>

consteval bool probe() {
  int* p = new int;  // indeterminate value, but the object is within its lifetime
  bool r = std::is_within_lifetime(p);
  delete p;
  return r;
}
static_assert(probe());

int main() {}
```

¶5 restricts which objects can be asked about: during the evaluation of an expression `E` as a core constant expression, `p` must point to an object that is [[g:usable-in-constant-expressions|usable in constant expressions]], or to an object whose complete object's lifetime began within `E`; otherwise the call is ill-formed.

The reason is that the constant evaluator only knows the state of these two kinds of objects. For an ordinary global variable, the compiler has no way of knowing at compile time whether at run time it has already been destroyed or recreated with placement new:

```cpp run title="within-lifetime-global.cpp" error
#include <type_traits>

int g;
constexpr bool b = std::is_within_lifetime(&g);  // error

int main() {}
```

Clang rejects this code, with a note that reading the non-const variable `g` is not allowed in a constant expression.

### The template parameter `U`

The function template in the current draft has an extra leading template parameter `U`, defaulting to `void`, and an extra condition for the return value: `static_cast<const volatile U*>(p)` must be a constant subexpression. When `U` is `void` this conversion is always possible, and the behavior is the same as in the original proposal.

When `U` is given explicitly, the same call can also answer whether `p` can be converted to `U*` during constant evaluation. For example, a downcast from a base class pointer to a derived class pointer: this `static_cast` is a constant subexpression only if the object really is of that derived class ([[expr.static.cast]], [[expr.const]]).

!!! impl "libc++ does not implement `U` yet"
    libc++ (with Clang 23) declares only one template parameter, `template <class _Tp> consteval bool is_within_lifetime(const _Tp* __p) noexcept`, which calls `__builtin_is_within_lifetime` internally; its feature-test macro `__cpp_lib_is_within_lifetime` is `202306L`, while in the current draft it is `202603L`. So with this toolchain, the `int` in `std::is_within_lifetime<int>(&x)` binds to `T`, not `U`.

## Questions

!!! question "Question"
    What does the following program print?

    ```cpp run ok
    #include <cstdio>
    #include <type_traits>

    constexpr int sz() {
      return std::is_constant_evaluated() ? 16 : 4096;
    }

    int main() {
      int n = sz();
      static int m = sz();
      std::printf("%d %d\n", n, m);
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `4096 16` (verified with Clang 23).

`n` is a non-`const` variable with automatic storage duration; its initialization is not manifestly constant-evaluated, so it gets `4096`. `m` is a variable with static storage duration; at initialization constant initialization is attempted first ([[basic.start.static]]), that attempt is manifestly constant-evaluated ([[expr.const]]), and it succeeds, so `m` is constant-initialized to 16.
</details>

## Quick reference

| Function | When `true` | Key points |
|---|---|---|
| `is_constant_evaluated()` | The call is manifestly constant-evaluated | Equivalent to `if consteval`; do not put it in `if constexpr` |
| `is_within_lifetime(p)` {{c++26}} | The object `p` points to is within its lifetime, and the conversion to `U*` is a constant subexpression | `consteval`; can only ask about objects usable in constant expressions or created during the current evaluation |
