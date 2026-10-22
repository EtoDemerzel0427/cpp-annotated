---
title: Numeric type requirements
summary: "complex and valarray may be instantiated only with numeric types (default constructible, copyable, destructible value types); an operation on the element type throwing is UB; valarray's members require the element type to support the corresponding operations only when used."
updated: 2026-10-19
---

!!! tldr
    - `complex` and `valarray` may be instantiated only with numeric types: cv-unqualified object types that are default constructible, copy constructible, copy assignable and destructible; intuitively, value types.
    - Meeting these four does not mean it works: `complex` is guaranteed only for floating-point types, and `complex<int>` has unspecified effects.
    - If any operation on the element type throws an exception, the behavior is undefined, so `valarray` provides no exception safety guarantees.
    - Many members of `valarray<T>` can be instantiated only when `T` supports the corresponding operations. `valarray<complex<double>>` is valid, but you cannot call `max()` or `>`.

## What a numeric type is (¶1)

¶1 `complex` and `valarray` are templates parameterized by the element type, and programs may instantiate them only with **numeric types**. A numeric type is a cv-unqualified object type that meets the four requirements *Cpp17DefaultConstructible*, *Cpp17CopyConstructible*, *Cpp17CopyAssignable* and *Cpp17Destructible* ([[utility.arg.requirements]]). Footnote 218 explains it as "in other words, value types": arithmetic types, pointers, `complex`, and `valarray` of value types.

This is only the threshold for getting in. `complex` has a stricter rule: instantiating the primary `complex` template with a type other than a cv-unqualified floating-point type has unspecified effects ([complex.numbers.general] ¶2 in [[complex.numbers]]). `int` is a numeric type, but the standard does not guarantee that `complex<int>` works.

This rule is a requirement on programs; the standard does not require compilers to diagnose it. Violating the library's requirements on template arguments is undefined behavior under the library's general rules ([[res.on.functions]]).

## An element operation throwing is UB (¶2)

¶2 If any operation on `T` throws an exception, the effects are undefined.

With this rule, the library does not have to provide any exception safety guarantees for assignment, addition and other operations on `valarray<T>`. Implementations are free to use expression templates, lazy evaluation and in-place overwriting without considering what state the array is in if an exception is thrown halfway through.

The consequence: if addition on `BigInt` may throw `bad_alloc` when out of memory, then addition on `valarray<BigInt>` is UB once it actually throws. [[numarray]] separately allows `valarray`'s own library functions to throw `bad_alloc` when resources are insufficient; that is a different matter.

## Members usable on demand (¶3, ¶4)

```cpp run title="valarray-complex.cpp" ok
#include <complex>
#include <valarray>

int main() {
  std::valarray<std::complex<double>> v{{1, 2}, {3, 4}};
  v *= std::complex<double>(0, 1);   // OK: complex has *=
  auto s = v.sum();                  // OK: sum requires only +=
  (void)s;
  // auto m = v.max();               // error: max needs <, which complex lacks
  // std::valarray<bool> b = v > v;  // error: same reason
}
```

¶3 Many members and related functions of `valarray<T>` can be successfully instantiated, and have well-defined behavior, only if `T` meets their additional requirements. ¶4's example is the code above: `valarray<complex<double>>` is a valid type, but `complex` has no ordering, so `operator>` cannot be instantiated.

This relies on on-demand instantiation of class template members ([[temp.inst]]): when a class template specialization is implicitly instantiated, only the declarations of member functions are instantiated, and the definitions wait until they are used. So `valarray<T>` can declare `max()` and `operator<` even if `T` has no `<`, as long as the program does not call them.

!!! impl "libc++'s expression templates"
    With libc++ in our tests, writing the last line as `auto b = v > v;` compiles. `v > v` returns an expression template object ([[numarray]] allows such replacement types), and the comparison is instantiated only when elements are evaluated. As long as the elements of `b` are never read, the error never appears.

!!! note "Compared with modern library components"
    This design, where members exist but may not be instantiable, is C++98 style. Newer library components use *Constraints* (`requires` clauses) to remove unusable members from overload resolution, so that `requires { v.max(); }` truthfully yields `false`. `valarray` has not been rewritten this way; concept checks on it give results that depend on whether the implementation happens to expose the error in a declaration, and cannot be relied on.

## Summary

| Rule | Paragraph | Consequence |
|---|---|---|
| `complex`/`valarray` may be instantiated only with numeric types | ¶1 | violation is UB; instantiating `complex` with a non-floating-point type has unspecified effects |
| an operation on `T` throws | ¶2 | UB; the library provides no exception safety guarantees |
| members are instantiated on demand | ¶3–¶4 | `valarray<complex<double>>` is usable, but `max`, `>` and the like cannot be called |
