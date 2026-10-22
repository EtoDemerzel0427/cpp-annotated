---
title: Address of an overload set
summary: "When a function name appears without arguments (taking its address, assigning it to a function pointer) and refers to a set of overloaded functions, the compiler picks exactly one by the target type the context requires: non-template functions need an identical type, templates are deduced, and constraints and partial ordering then eliminate down to one."
updated: 2026-10-19
---

!!! tldr
    - When an overloaded function name appears without arguments, as in `int (*p)(int) = &f;`, the compiler picks a function by the target type: initialization, assignment, function arguments, return values, explicit conversions and constant template arguments can all supply one.
    - A non-template function's type must be identical to the target's; the only allowed conversion is dropping `noexcept`. No implicit conversions, no covariance.
    - Function templates deduce their template arguments from the target type. Then elimination happens in order: those whose constraints aren't satisfied, template specializations when non-templates exist, less constrained non-templates, less specialized template specializations; exactly one must remain.
    - When the target is a template parameter there's no definite target type, so things like `std::function<int(int)> fn = f;` and `std::transform(..., std::toupper)` fail when `f` is overloaded.

## Choosing a function by target type

```cpp run ok
int f(double) { return 1; }
int f(int)    { return 2; }

int (*p1)(int) = &f;       // picks f(int)
int (&r1)(double) = f;     // picks f(double)

int main() {
  return p1(0) + r1(0) - 3;
}
```

When calling `f(1)`, the compiler chooses an overload by the types of the arguments; that's overload resolution in [[over.match]]. A function name can also appear without arguments: taking its address, assigning it to a function pointer, passing it to a function that takes a function pointer. There are no arguments to look at then, so the standard works in the other direction: it looks at what type the expression is to be converted to and picks the function whose type agrees with it. That type is called the **target type**.

When the declarations found by name lookup are all functions or function templates, they form an [[g:overload-set|overload set]] ([[basic.lookup.general]]), even if there's only one function. A name that refers to an overload set has to go through overload resolution, or through the rules of this subclause, to select a single function ([[expr.prim.id]]).

The rules here are almost entirely independent of [[over.match]]: no implicit conversion sequences, no ranking; just whether the types are identical, plus a few elimination rules.

## Which contexts supply a target (¶1)

¶1 An expression that refers to an overload set `S` and appears without arguments resolves to a specific function itself, a pointer to it, or a pointer to member function. The function is selected from `S` by the target type the context requires. The target can be:

| Item | Target | Example |
|---|---|---|
| ¶1.1 | an object or reference being initialized | `int (*p)(int) = f;`, `S s{f};` |
| ¶1.2 | the left side of an assignment | `p = &f;` |
| ¶1.3 | a parameter of a function | `take(f)`, where `take`'s parameter is `int(*)(int)` |
| ¶1.4 | a parameter of a user-defined operator | `std::cout << std::endl` |
| ¶1.5 | the return value of a function, operator function or conversion function | `return &f;` |
| ¶1.6 | an explicit type conversion | `static_cast<int(*)(int)>(f)` |
| ¶1.7 | a constant template parameter | `X<f>`, where `X`'s parameter is `int(*)(double)` |

If the target type contains a placeholder type (`auto`, `decltype(auto)`), placeholder type deduction ([[dcl.type.auto.deduct]]) is done first, and the rest of this subclause uses the deduced type. The expression may be preceded by `&`. Note 1 adds that redundant parentheses around the function name are ignored ([[expr.prim.paren]]), except when forming a pointer to member; see Example 2 below.

The following have no usable target:

```cpp error
int f(int);
int f(double);
auto a = &f;               // error: the two candidates deduce different types
using T = decltype(&f);    // error: no target
void g() { (void)&f; }     // error: no target
```

`decltype(&f)` and `(void)&f` have no target. By ¶2, all non-template functions are then selected; there are two, so it's ill-formed. `auto a = &f;` must deduce `auto` first, and the two candidates give different types, so deduction fails (see the discussion of Example 3 below).

Template parameters don't supply a target either. In `template<class T> void call(T); call(f);` the parameter type `T` itself is still to be deduced; [[temp.deduct.call#6]] specifies that deduction is then only tried for each member in turn; see the `std::toupper` example below.

## Non-template functions: identical type (¶2)

¶2 With no target, all the non-template functions referred to are selected. With a target, a non-template function is selected if and only if its function type is identical to the function type of the target, after possibly applying a function pointer conversion ([[conv.fctptr]]).

Identical means no implicit conversions at all: a parameter type or return type that's slightly off won't do. In the standard's Example 1, `int (*pfe)(...) = &f;` is ill-formed, not because two candidates are ambiguous but because there's no `f` of type `int(...)` at all. Likewise, `long (*q)(int) = k;` is ill-formed for a `k` returning `int`.

The only exception is the function pointer conversion, which allows dropping `noexcept`:

```cpp
void f(int) noexcept;
void f(double);
void (*p)(int) = f;                // OK: void(int) noexcept with noexcept dropped
void (*q)(double) noexcept = f;    // error: can't add noexcept
```

Note 2 explains that when matching a pointer-to-member-function type, the class of the member is ignored. The target `void (D::*)()` can select the base class member `B::f()`; `&D::f` has type `void (B::*)()` and then becomes `void (D::*)()` through a pointer-to-member conversion ([[conv.mem]]):

```cpp run ok
struct B { void f() {} void f(int) {} };
struct D : B {};
void (D::*p)() = &D::f;      // picks B::f(), then converts to void (D::*)()
void (B::*q)(int) = &D::f;   // picks B::f(int)
int main() { D d; (d.*p)(); (d.*q)(1); }
```

¶8 Note 5 points out that even if `B` is a public base of `D`, there's no covariance or contravariance in return types or parameter types:

```cpp error
struct B {}; struct D : B {};
D* f();
B* (*p1)() = &f;     // error
void g(D*);
void (*p2)(B*) = &g; // error
```

## Function templates: deduce from the target (¶3)

```cpp run ok
template<class T> T twice(T x) { return x + x; }
int (*p)(int) = &twice;        // T = int deduced from the target type
auto q = &twice<double>;       // no target, but T is given explicitly
int main() { return p(1) + int(q(0.5)) - 3; }
```

¶3 For each function template referred to, template argument deduction is performed ([[temp.over]], [[temp.deduct.funcaddr]], [[temp.arg.explicit]]); if it succeeds, the resulting specialization is added to the candidates. With a target, deduction uses the template's function type and the target type; without a target, all template arguments must be given explicitly or have defaults ([[temp.deduct.funcaddr]]).

## Which kind of member function matches which target (¶4)

¶4 Non-member functions, static member functions and explicit object member functions (C++23 member functions with a `this` parameter) match targets of function pointer or function reference type; implicit object member functions, that is, ordinary non-static member functions, match targets of pointer-to-member-function type.

```cpp run ok
struct S {
  int f(this S) { return 1; }   // explicit object member function
  int f(int) { return 2; }      // implicit object member function
};
int (*p)(S)      = &S::f;       // picks f(this S), type int(*)(S)
int (S::*q)(int) = &S::f;       // picks f(int)
int main() { S s; return p(s) + (s.*q)(0) - 3; }
```

Explicit object member functions are like static member functions in this respect: `&S::f` is an ordinary function pointer, with the object parameter becoming the first parameter. Note 3 points out that when an implicit object member function is selected, the result can only be used to form a pointer to member, that is, it must be written `&X::f` ([[expr.unary.op]]).

The standard's Example 2 puts these together and also shows what parentheses do:

```cpp error
struct X {
  int f(int);
  static int f(long);
};
int (X::*p1)(int)  = &X::f;    // OK
int    (*p2)(int)  = &X::f;    // error: f(int) doesn't match a function pointer
int    (*p3)(long) = &X::f;    // OK
int (X::*p4)(long) = &X::f;    // error: a static member function doesn't match a pointer to member function
int (X::*p5)(int)  = &(X::f);  // error: parentheses prevent forming a pointer to member
int    (*p6)(long) = &(X::f);  // OK
```

A pointer to member is formed only when `&` applies directly to the qualified name `X::f` ([[expr.unary.op]]), and `&(X::f)` doesn't have that form. This is the exception to note 1's rule that redundant parentheses are ignored.

## Eliminating down to one (¶5)

```cpp run ok
template<class T> int g(T)  { return 1; }
int g(int)                  { return 2; }
template<class T> int h(T)  { return 3; }
template<class T> int h(T*) { return 4; }

int (*pg)(int)  = g;   // g(int)
int (*ph)(int*) = h;   // h(T*)
int main() { return pg(0) + ph(nullptr) - 6; }
```

¶5 The set of candidates is pruned in the following order:

1. Remove the functions whose associated constraints aren't satisfied ([[temp.constr.decl]]).
2. If more than one remains and the set contains a non-template function, remove all function template specializations.
3. Remove a non-template function `F0` if another non-template function is more partial-ordering-constrained than it ([[temp.constr.order]]).
4. Remove a function template specialization `F1` if the template of another function template specialization is more specialized than `F1`'s template according to [[temp.func.order]].

After elimination exactly one function must remain, otherwise the program is ill-formed.

In the example above, the candidates for `pg` are `g<int>` and `g(int)`, and step 2 removes the template specialization. The candidates for `ph` are `h<int*>` (from `h(T)`) and `h<int>` (from `h(T*)`), and step 4 keeps the more specialized `h(T*)`. Steps 2 and 4 correspond to the tie-breakers "non-template preferred" and "more specialized template preferred" in [[over.match.best]].

### Constraints are compared only when parameters are the same

The standard's Example 3:

```cpp error
template<bool B> struct X {
  void e(int) requires B;   // #1
  void e(int);              // #2
  void f(short) requires B;
  void f(long);
  template<typename> void g(short) requires B;
  template<typename> void g(long);
};
void test() {
  auto ep = &X<true>::e;    // OK: picks #1
  &X<true>::f;              // error: ambiguous
  &X<true>::g<int>;         // error: ambiguous
}
```

`auto ep = &X<true>::e;` deduces `auto` first. [[temp.deduct.call#6.2]] specifies that deduction is tried for each member of the overload set, and if all successful deductions give the same type, that's the result. #1 and #2 both have type `void (X<true>::*)(int)`, so deduction succeeds. Then both agree with the target, and in step 3 #1 is more constrained than #2, so #2 is removed.

`&X<true>::f` has no target, so both non-template functions are selected. Their parameter types differ, and per [[temp.constr.order]] it can't then be determined which is more constrained, so both remain: ambiguous. `&X<true>::g<int>` is the same: the two templates have different parameters, and neither partial ordering nor constraints can tell them apart. So constraints aren't a tie-breaker in the general sense.

If the only function's constraints aren't satisfied, the set becomes empty:

```cpp error
template<class T> struct A {
  static void g() requires (sizeof(T) > 100);
};
auto p = &A<int>::g;   // error: constraints not satisfied
```

!!! lawyer "Placeholder types and overload sets"
    Deducing first and then selecting when the target contains a placeholder type, and the rule in [[temp.deduct.call#6.2]] that it suffices for all successful deductions to give the same type, are both new wording after C++23. The effect is that `auto p = &X<true>::e;`, where all candidate types are the same and only constraints distinguish them, is valid; while with `f(int)` and `f(double)` both present, `auto p = &f;` is still ill-formed, because the two deductions give different types. Clang 23 already implements this in our tests.

## When two overload sets meet (¶7)

```cpp run ok
int g(int)    { return 1; }
int g(double) { return 2; }
int f(int (*p)(int))  { return 10 + p(0); }
int f(int (*p)(char)) { return 20 + p(0); }   // there's no g(char)
int main() { return f(g) - 11; }               // f(int(*)(int)), g(int)
```

¶7 Note 4 points out that when `f` and `g` are both overload sets, resolving `f(&g)` or `f(g)` has to consider all combinations: for each candidate `f`, the type of the corresponding parameter is used as the target type for `g`, and that `f` is viable only if a function can be selected from `g`. In the example, the second `f` can't find a `g(char)` and isn't viable.

If both `f` can be paired with a `g`, ordinary overload resolution follows, and since the conversions on both sides are exact matches, the result is ambiguous (Question 2).

## `std::endl` and `std::toupper`

`std::cout << std::endl` works: `std::endl` is a function template, and `basic_ostream` has a member `operator<<(basic_ostream& (*pf)(basic_ostream&))` whose parameter is a concrete function pointer type; by ¶1.4 it supplies the target, from which `std::endl`'s template arguments are deduced.

Passing `std::toupper` to `std::transform`, however, often fails to compile:

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
void up(std::string& s) {
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);   // error
}
```

The fourth parameter of `std::transform` has the template parameter type `UnaryOp`, which supplies no target. The argument `std::toupper` is an overload set: `int toupper(int)` from `<cctype>`, plus the function template `toupper(charT, const locale&)` from `<locale>`. By [[temp.deduct.call#6.1]], when the overload set contains a function template the parameter is a non-deduced context, so `UnaryOp` can't be deduced. If only `<cctype>` were included, the overload set would contain a single non-template function and the trial deduction would succeed. So whether this code compiles depends on indirect inclusion between standard library headers.

Even when it compiles, writing it this way isn't portable. [[namespace.std#6]] specifies that unless a standard library function is designated an addressable function, the behavior of forming a pointer to it is unspecified (possibly ill-formed); `toupper` isn't such a function. Also, passing a negative `char` value to `toupper(int)` is UB. Use a lambda:

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return s == "ABC" ? 0 : 1;
}
```

`std::function<int(int)> fn = f;` fails when `f` is overloaded for the same reason: `std::function`'s converting constructor is a template. You can write `static_cast<int(*)(int)>(f)`, or wrap it in a lambda, where the call inside is an ordinary call that goes through [[over.match]].

## Implementation view

!!! impl
    - Compilers call this resolving the address of an overloaded function. On a type mismatch Clang reports "address of overloaded function 'f' does not match required type …"; without a target it reports "reference to overloaded function could not be resolved; did you mean to call it?"; when `auto` deduction fails it reports "variable 'a' with type 'auto' has incompatible initializer of type '&lt;overloaded function type&gt;'".
    - What is compared is the function type after declaration adjustment: top-level `const` on parameters and the adjustment of array and function parameters to pointers have already happened ([[dcl.fct]]), so `void f(const int)` agrees with the target `void(*)(int)`.
    - Compilers implement this step as a special case of implicit conversion: when the source of an initialization or conversion is an overload set, they first select a function by the target type, then perform the ordinary function-to-pointer and function pointer conversions.

## History

!!! history
    - C++98 already had target types, non-template preference, more-specialized-template preference, and the requirement that exactly one remain.
    - C++17 made `noexcept` part of the function type, and ¶2 allows a function pointer conversion before comparison.
    - C++20 added the constraint rules of ¶5 along with concepts: first remove functions whose constraints aren't satisfied, then compare constraints among non-template functions.
    - C++23's explicit object member functions ([[P0847R7]]) were written into ¶4, matching function pointers like static member functions.
    - Wording after C++23 specifies deducing first and then selecting when the target contains a placeholder type.

## Common misconceptions

!!! pitfall "Selection performs implicit conversions"
    When `f` returns `int`, `long (*p)(int) = f;` is ill-formed. Only identical types count here; the only allowance is dropping `noexcept`.

!!! pitfall "An overloaded function can be passed directly to a template parameter"
    The parameters of `std::thread t(f, 1);`, `std::invoke(f, 1)` and `std::bind(f, _1)` are all templates with no target type, so they all fail when `f` is overloaded. Convert to a concrete pointer type with `static_cast`, or wrap it in a lambda.

!!! pitfall "You can freely take the address of standard library functions"
    Unless the standard designates it an addressable function, taking the address of a function in `std::` (including implicitly, by passing the function name) is unspecified and possibly ill-formed. Implementations are entitled to add overloads to these functions or turn them into function templates.

## Questions

!!! question "Question 1"
    Which of these declarations are well-formed?
    ```cpp
    void f(int);
    void f(long);
    template<void (*P)(long)> struct Y {};
    Y<f> y1;
    Y<&f> y2;
    void (*arr[2])(int) = { f, &f };
    auto g = static_cast<void (*)(int)>(f);
    decltype(f)* h = f;
    ```

<details markdown="1">
<summary>Answer</summary>

The first four (`y1`, `y2`, `arr`, `g`) are well-formed: a constant template parameter (¶1.7), each element initialized in an aggregate initialization (¶1.1), and an explicit type conversion (¶1.6) all supply a target.

`decltype(f)* h = f;` is ill-formed: the `f` in `decltype(f)` has no target, so by ¶2 both non-template functions are selected, not exactly one.
</details>

!!! question "Question 2"
    After `int g(int); int g(double); int f(int (*)(int)); int f(int (*)(double));`, what is the result of `f(g);`?

<details markdown="1">
<summary>Answer</summary>

Ambiguous. By ¶7, both `f` are viable: the first pairs with `g(int)`, the second with `g(double)`. Next comes ordinary overload resolution ([[over.match.best]]), where the argument conversion on both sides is just a function-to-pointer conversion, an exact match, so they can't be told apart. In our tests Clang 23 reports "call to 'f' is ambiguous".
</details>
