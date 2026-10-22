---
title: Exam 4 · Templates, deduction and constraints
summary: 25 questions on two-phase lookup and dependent names, the various sources of IFNDR, template argument deduction and SFINAE, partial ordering and specialization, CTAD, constraint satisfaction and subsumption, NTTPs, fold expressions, and discarded statements of if constexpr.
tags: exam, templates, two-phase lookup, template argument deduction, SFINAE, CTAD, concepts, IFNDR
updated: 2026-10-20
---

!!! tldr
    - Scope: [[temp.res]], [[temp.dep]], [[temp.point]], [[temp.deduct]], [[temp.func.order]], [[temp.spec.partial]], [[temp.expl.spec]], [[over.match.class.deduct]], [[temp.alias]], [[temp.constr]], [[temp.param]], [[temp.variadic]], [[stmt.if]].
    - 25 questions: 15 verdict, 7 multiple choice, 3 open-ended, roughly increasing in difficulty. Non-template lookup and overloading, initialization, constant evaluation, and C++26 pack indexing and reflection each have their own exam.
    - For verdict questions, answer with the most severe property of the whole program; every IFNDR question maps to a paragraph that says "no diagnostic required".
    - Suggested time: 75 minutes. Answer from the code and the wording first, then check with a compiler; on IFNDR questions, whether the compiler reports an error is no basis for the verdict.

## 1. Dependent names, disambiguation, and templates with no valid specialization

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does the program print?

```cpp run
#include <cstdio>
int x = 42;
template<class T> struct B { int x = 0; };
template<class T> struct D : B<T> {
  int f() { return x; }
};
int main() { D<int> d; std::printf("%d\n", d.f()); }
```

- A. `0`
- B. `42`
- C. The program is ill-formed: `x` is ambiguous
- D. The program is IFNDR; the output is unpredictable

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B; it prints `42`.**

1. The `x` in `return x;` is an unqualified name that is not in a dependent call and is not a member of the current instantiation, so it is not a dependent name. A non-dependent name is looked up once at the point of the template definition and bound there ([[temp.res.general#1]]).
2. Class-scope lookup at the point of definition searches only non-dependent bases ([[class.member.lookup#4]]). `B<T>` depends on `T`, so it is a **dependent base class** ([[temp.dep.type#3]]), and its members are not visible at the point of definition.
3. Lookup continues outward and finds the global `::x`. When `D<int>` is instantiated, `x` is not looked up again, and `B<int>::x` never gets to take part, so there is no ambiguity and no IFNDR.

Those who choose A assume `x` is looked up again at instantiation, but only dependent names are. To access the base class member, write `this->x` or `B<T>::x`: in both forms the lookup context depends on `T`, which makes the name dependent ([[temp.dep.type#5]], items 5.2 and 5.4).

```cpp run ok
#include <cstdio>
int x = 42;
template<class T> struct B { int x = 0; };
template<class T> struct D : B<T> {
  int f() { return this->x; }
};
int main() { D<int> d; std::printf("%d\n", d.f()); }   // prints 0
```

See [[topics/two-phase-lookup]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

Since C++20, none of the `T::R`, `T::P` and `T::Ptr` below is written with `typename`. In which one is `T::R` not treated as a type?

```cpp
template<class T> struct S {
  T::R f(T::P p);              // (A) member declaration of a class template
  using Ptr = T::Ptr;          // (D) alias declaration
};
template<class T> T::R g();    // (B) namespace scope, return type
template<class T> void h(T::R);// (C) namespace scope, parameter type
```

- A. (A)
- B. (B)
- C. (C)
- D. (D)

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

[[P0634R3]] introduced **type-only contexts**: a dependent qualified name appearing in one of these positions is taken to be a type ([[temp.res.general#5]]). Checking each against [[temp.res.general#4]]:

- In (A), the return type is a *decl-specifier* of a member declaration (item 4.4.2), and the parameter is a *parameter-declaration* in a member declaration (item 4.4.3).
- (B) is a *decl-specifier* of a *simple-declaration* at namespace scope (item 4.4.1).
- (D) is a *defining-type-id* (item 4.3.2).
- The parameter in (C) is not on the list. Item 4.4.4 covers only function declarations whose *declarator-id* is qualified, and `h`'s is not.

So (C) is parsed by the default rule: `T::R` is an expression, and the whole statement declares a variable template `h` of type `void`, initialized with `(T::R)`. A `void` variable can never be valid, so this variable template has no valid specialization, and the program is IFNDR ([[temp.res.general#6]], item 6.1). Example 5 in [[temp.res.general#4]] is exactly this line. Clang reports `variable has incomplete type 'void'` right at the definition, which IFNDR permits.

Writing `void h(typename T::R)`, or defining a member out of class as `template<class T> void S<T>::h(T::R)` (where the *declarator-id* is qualified), both correctly declare a function template. A block-scope `T::R x;` is also not on the list and likewise needs `typename`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program. `f` is never called.

```cpp run
template<class T> void f(T) {
  static_assert(false, "f must not be instantiated");
}
int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

1. [[dcl.pre#13]] says that if the expression of a *static_assert-declaration* is evaluated in the context of a template definition, the declaration has no effect. It is actually checked only on instantiation.
2. Item 6.1 of [[temp.res.general#6]] explicitly excludes failed *static_assert-declaration*s when deciding whether a valid specialization exists, so one cannot say that `f` has no valid specialization.
3. `f` is never instantiated, the `static_assert` never fails, and the program is well-formed.

The rule comes from [[P2593R1]]. Before it, `static_assert(false)` did not depend on a template parameter and would fail for every specialization, making the program IFNDR, which is where the `ifndr` distractor comes from. The old workaround was a dependent expression such as `static_assert(sizeof(T) == 0)`. Strictly speaking, that form has no valid specialization either and was IFNDR under the old rule too; compilers just could not detect it.

Once `f(1)` is called, the `static_assert` fails on instantiation and the program is ill-formed ([[dcl.pre#13]], item 13.1).

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

Judge the whole program. `f` is never called.

```cpp run
template<class T> void f(T) {
  int a[-static_cast<int>(sizeof(T) / sizeof(T))];
  (void)a;
}
int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: IFNDR.**

1. An array bound must be a converted constant expression of type `std::size_t` whose value is greater than zero ([[dcl.array#1]]). For every `T` for which `sizeof(T)` is valid, `sizeof(T) / sizeof(T)` is 1 and the bound is `-1`; converting it to `size_t` is a narrowing conversion, so it is not a converted constant expression. When `sizeof(T)` itself is invalid, it is an error anyway.
2. So this function template has no valid specialization, and it is never instantiated. Item 6.1 of [[temp.res.general#6]]: the program is ill-formed, no diagnostic required.

Clang gives no diagnostic, which IFNDR permits. The argument for `ok` is "nothing is checked without instantiation", but the standard makes no such promise: a template with no valid specialization makes the program erroneous even if it is never instantiated; the compiler is just allowed to stay silent.

Compare with the previous question: there the only problem was a failed `static_assert`, which item 6.1 explicitly excludes; here the problem is the array bound, which is not excluded.

With the bound written as `-static_cast<int>(sizeof(T))`, things are less clear-cut: when `sizeof(T)` exceeds `INT_MAX`, the conversion to `int` wraps around (modulo 2<sup>32</sup> for a 32-bit `int`). On a 64-bit platform with `T = char[3000000000]`, the bound is the positive number 1294967296; in our tests Clang accepts `f<char[3000000000]>(nullptr)`, so the template does have a valid specialization.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

Judge the whole program.

```cpp run
#include <cstdio>
namespace N {
  struct A {};
  int h(A, long) { return 1; }
}
template<class T> int g(T t) { return h(t, 0); }
int x = g(N::A{});
namespace N {
  int h(A, int) { return 2; }
}
int main() { std::printf("%d\n", x); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: IFNDR.**

1. The argument `t` in `h(t, 0)` is type-dependent, so this is a dependent call ([[temp.dep.general#2]], item 2.2). Ordinary unqualified lookup at the point of definition finds no `h`; at instantiation, ADL is performed in the instantiation context, with associated namespace `N` ([[basic.lookup.argdep#4]]).
2. `g<N::A>` has two **points of instantiation**: immediately after the namespace-scope declaration `int x = g(N::A{});` ([[temp.point#1]]), and the end of the translation unit ([[temp.point#7]], item 7.1).
3. At the first point, ADL can find only `h(A, long)`, and that is what gets called; at the end of the TU, `h(A, int)` is also visible and is an exact match for `0`, so it would be selected.
4. The two points of instantiation give different meanings; per [[temp.point#7]], the program is ill-formed, no diagnostic required.

In our tests Clang prints `2`, because Clang defers the instantiation of function templates to the end of the TU. Other implementations might print `1`; neither is a result the standard guarantees. Move `h(A, int)` before the template definition and both points of instantiation see the same thing; the program is well-formed and prints `2`.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`B<T>` is a dependent base of `D<T>`, and `B<T>` has a member function `g`. Inside a member function of `D<T>`, how is `g` looked up in each of the four forms below? Which one suppresses virtual dispatch? Which one compiles on old compilers that do not implement two-phase lookup but not on Clang?

```cpp
template<class T> struct D : B<T> {
  int a() { return g(); }          // (1)
  int b() { return this->g(); }    // (2)
  int c() { return B<T>::g(); }    // (3)
  using B<T>::g;                   // (4) then write g() in member functions
};
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Reference answer:**

(1) `g()` has no arguments, so it is not a dependent call ([[temp.dep.general#2]]), and `g` is a non-dependent name, looked up once at the point of definition. Dependent bases are not searched ([[class.member.lookup#4]]); if there is no other `g` in an enclosing scope, lookup fails and the program is ill-formed; if there is a `::g`, the name silently binds to it (see question 1). Old compilers without two-phase lookup look the name up again at instantiation, so it "compiles" there, while Clang reports `use of undeclared identifier 'g'`.

(2) `this->g` is class member access whose lookup context is the current instantiation; the current instantiation has a dependent base and `g` is not found at definition, so the name is dependent ([[temp.dep.type#5]], item 5.4) and is found in `B<int>` at instantiation. The call behaves like an ordinary member call; if `g` is virtual, it is dispatched dynamically as usual.

(3) The lookup context of `B<T>::g` is a dependent type, so the name is dependent ([[temp.dep.type#5]], item 5.2) and is found at instantiation. But it is a call with a qualified name, and such calls do not use virtual dispatch ([[class.virtual#16]]): even if a derived class overrides `g`, `B<T>::g` is the one called.

(4) The *nested-name-specifier* of the *using-declarator* depends on `T`, and the declaration introduces `B<T>::g` into the scope of `D<T>`. A later unqualified `g()` finds this using-declaration at the point of definition, and at instantiation it is replaced by the declarations in `B<int>` ([[temp.res.general#1]], note 1). Virtual dispatch is unaffected.

```cpp run ok
#include <cstdio>
template<class T> struct B {
  virtual int g() { return 1; }
  virtual ~B() = default;
};
template<class T> struct D : B<T> {
  int call_this() { return this->g(); }
  int call_qual() { return B<T>::g(); }
};
struct E : D<int> { int g() override { return 2; } };
int main() {
  E e;
  std::printf("%d %d\n", e.call_this(), e.call_qual());   // prints 2 1
}
```

</details>
</div>

## 2. Argument deduction, SFINAE and partial ordering

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
template<class T> void f(T, T) {}
void g() {}
int main() { f(g, &g); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

1. Neither parameter type `T` is a reference. [[temp.deduct.call#2]], item 2.2: if the argument type `A` is a function type, the type produced by the function-to-pointer conversion is used for deduction.
2. The first argument `g` has type `void()`, which becomes `void(*)()` for deduction; the second argument `&g` is already `void(*)()`. Both deduce `T = void(*)()`, with no conflict.

Reference parameters are different: no decay happens for a reference parameter, so `T` is deduced as `void()` and `void(*)()` respectively, and deduction fails.

```cpp run error
template<class T> void f(const T&, const T&) {}
void g() {}
int main() { f(g, &g); }   // error: T deduced as void() and void(*)()
```

Arrays behave the same way: `f(T, T)` accepts `f("abc", "ab")` (both decay to `const char*`), whereas `f(const T&, const T&)` would deduce `char[4]` and `char[3]`, and deduction fails.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

Which of the five calls below deduce successfully?

```cpp
#include <cstddef>
#include <initializer_list>
#include <vector>
template<class T> void a(T);
template<class T> void b(std::initializer_list<T>);
template<class T, std::size_t N> void c(T (&&)[N]);
template<class T> void d(std::vector<T>);

void test() {
  a({1, 2});      // (1)
  b({1, 2});      // (2)
  b({});          // (3)
  c({1, 2, 3});   // (4)
  d({1, 2});      // (5)
}
```

- A. (2)(4)
- B. (2)(3)(4)
- C. (2)(4)(5)
- D. (1)(2)(4)(5)

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A.**

[[temp.deduct.call#1]] specifies deduction from a braced list for only two parameter forms: after removing references and cv-qualifiers, `std::initializer_list<P′>` or `P′[N]`, and only when the argument is a **non-empty** list. Each element is then treated as a separate argument for deducing `P′`, and if `N` is a constant template parameter it is deduced from the number of elements. Otherwise a braced list makes the parameter a non-deduced context ([[temp.deduct.type#5]], item 5.9).

- (1) The parameter is `T`, neither of the two forms, so `T` cannot be deduced. Fails.
- (2) `T = int`. Succeeds.
- (3) The list is empty, so the special rule of paragraph 1 does not apply; the parameter becomes a non-deduced context and `T` cannot be deduced. Fails.
- (4) `T (&&)[N]` without the reference is `T[N]`, deducing `T = int` and `N = 3`. Succeeds.
- (5) `std::vector<T>` does have an initializer-list constructor, but it is not `initializer_list<P′>`, and deduction rules do not look at constructors. Fails.

Those who choose C think `vector<T>` can be deduced "through" its constructor. Deduction only matches types; it does not perform overload resolution. To make (5) work, write `d<int>({1, 2})`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
template<class T> struct W { using type = typename T::type; };
template<class T> int f(typename W<T>::type*) { return 1; }
template<class T> int f(...) { return 2; }
int main() { return f<int>(nullptr); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. For the first `f`, substituting the explicit argument `T = int` into the function type requires `W<int>::type`. Looking up a class member needs a complete class, so `W<int>` is implicitly instantiated ([[temp.inst#2]]).
2. Instantiating `W<int>` makes the member alias `typename int::type` ill-formed. This error occurs in the instantiation of a class template specialization, not in the function type of `f` itself.
3. [[temp.deduct.general#8]]: an invalid type or expression is a deduction failure only if it occurs in the **immediate context** of the substitution; constructs instantiated separately are not part of the immediate context, and note 7 also says that side effects such as instantiating template specializations can make the program ill-formed. So this is not SFINAE but a hard error, and the second `f` never gets a chance to be selected.

Drop `W` and write `typename T::type*` directly: `int::type` then appears in the function type of `f`, which is the immediate context; deduction fails, and the call falls through to `f(...)`, returning 2:

```cpp run ok
template<class T> int f(typename T::type*) { return 1; }
template<class T> int f(...) { return 2; }
int main() { return f<int>(nullptr); }   // returns 2
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does the program print?

```cpp run
#include <cstdio>
template<class T> int f(T)        { return 1; }
template<class T> int f(T*)       { return 2; }
template<class T> int f(const T*) { return 3; }
int main() {
  int i = 0;
  const int* p = &i;
  std::printf("%d%d\n", f(p), f(&i));
}
```

- A. `33`
- B. `32`
- C. `22`
- D. The program is ill-formed: `f(&i)` is ambiguous

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B; it prints `32`.**

`f(p)`, with argument type `const int*`: the three templates deduce `T = const int*`, `T = const int` and `T = int` respectively, all exact matches, so partial ordering decides. Deducing #2's `T*` from #3's transformed type `const U*` gives `T = const U`, success; deducing `const T*` from `U*` in the other direction fails. So #3 is more specialized than #2, and #2 is more specialized than #1 ([[temp.deduct.partial#10]], [[temp.func.order#2]]); #3 is selected.

`f(&i)`, with argument type `int*`: #1 deduces `T = int*` and #2 deduces `T = int`, both identity conversions; #3 deduces `T = int`, and its parameter `const int*` needs a qualification conversion. Conversion sequences are compared first: the identity conversion is a proper subsequence of any non-identity sequence, so #1 and #2 are both better than #3 ([[over.ics.rank#3]], item 3.2.1). Partial ordering is used only when the conversion sequences cannot be distinguished ([[over.match.best.general#2]], item 2.5), and #3 is already out before that step. Of the remaining #1 and #2, #2 is more specialized, and the result is 2.

Those who choose A put partial ordering before conversion sequences. Partial ordering is a tie-breaker; it cannot overturn the comparison of conversion sequences.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
template<class T, class U> struct S { static constexpr int v = 0; };
template<class T>          struct S<T, T*>  { static constexpr int v = 1; };
template<class T, class U> struct S<T*, U*> { static constexpr int v = 2; };
int main() { return S<int*, int**>::v; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. Matching ([[temp.spec.partial.match#2]]): the first partial specialization deduces `T = int*`; the second deduces `T = int`, `U = int*`. Both match.
2. Partial ordering ([[temp.spec.partial.order#1]]): rewrite the two partial specializations as function templates `f(X<T, T*>)` and `f(X<T*, U*>)` and compare them.
   - Deducing `X<T*, U*>` from `X<A, A*>` (`A` a synthesized unique type): `T*` cannot be deduced from `A`. Fails.
   - Deducing `X<T, T*>` from `X<B*, C*>`: the first position gives `T = B*`, the second gives `T = C`, a conflict. Fails.
3. Both directions fail, so neither is more specialized than the other. [[temp.spec.partial.match#1]], item 1.2: the use of the template is then ambiguous, and the program is ill-formed. Clang reports `ambiguous partial specializations`.

Intuitively, `S<T, T*>` requires the second argument to have exactly one more level of pointer than the first, and `S<T*, U*>` requires both arguments to be pointers; neither condition contains the other, so neither side is more specialized. Add a `template<class T> struct S<T*, T**>`, which is more specialized than both, and the program becomes well-formed.

</details>
</div>

## 3. Specialization, alias templates and CTAD

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
#include <cstdio>
template<class T> using Ptr = T*;
template<class T> int f(Ptr<T>);
template<class T> int f(T*) { return 2; }
int main() { int i = 0; std::printf("%d\n", f(&i)); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; it prints `2`.**

1. A specialization of an alias template is equivalent to the type obtained by substituting its arguments ([[temp.alias#2]]); `Ptr<T>` is just `T*`.
2. So the two declarations have the same parameter types and template heads; they correspond ([[basic.scope.scope#4]], item 4.5) and declare the same function template. The first is a declaration, the second its definition.
3. The call has a single candidate, with `T = int`, and prints `2`.

Make the first one a definition too and the same function template is defined twice, violating [[basic.def.odr#2]]:

```cpp error
template<class T> using Ptr = T*;
template<class T> int f(Ptr<T>) { return 1; }
template<class T> int f(T*) { return 2; }   // error: redefinition of 'f'
```

The distractor is "two overloads, ambiguous call". An alias template creates neither a new type nor a new template; it is completely transparent when declarations are matched.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

Judge the whole program.

```cpp run
template<class T> int f(T) { return 0; }
int a = f(1);
template<> int f(int) { return 1; }
int main() { return a; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: IFNDR.**

1. `int a = f(1);` odr-uses `f<int>`, which needs its definition, so it is implicitly instantiated ([[temp.inst#5]]).
2. [[temp.expl.spec#7]]: if a template is explicitly specialized, a declaration of that specialization must be reachable from every use that would cause an implicit instantiation; no diagnostic is required for a violation. Here the explicit specialization comes after the use, and the program is IFNDR.

Clang can see the problem within one TU and reports `explicit specialization of 'f<int>' after instantiation`, a diagnostic IFNDR permits. When the use and the explicit specialization are in two different TUs, the compiler usually has no way to notice; see question 25.

Not every mention causes an instantiation. If the earlier mention is only inside `decltype` and the return type is spelled out, no function definition is needed, and a later explicit specialization is valid:

```cpp run ok
template<class T> int f(T) { return 0; }
using R = decltype(f(1));            // does not need the definition of f<int>
template<> int f(int) { return 1; }
int main() { return f(1); }
```

Change the return type to `auto` and `decltype(f(1))` needs the return type deduced, which requires instantiating the definition ([[dcl.spec.auto.general#15]]), and we are back to IFNDR.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
template<class T> struct Box { Box(T&&) {} };
int main() { int i = 0; Box b(i); (void)b; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. The constructor `Box(T&&)` yields the implicit deduction guide `template<class T> Box(T&&) -> Box<T>` ([[over.match.class.deduct#1]], item 1.1). There is also the copy deduction candidate `Box(Box<T>)`, which does not match the argument `int`.
2. The definition of a **forwarding reference** in [[temp.deduct.call#3]] excludes one case: during class template argument deduction, a `T&&` where `T` represents a template parameter of the class template is not a forwarding reference. So an lvalue argument does not make `T` deduce as `int&`.
3. By the ordinary rules `T` is deduced as `int`, the guide's parameter is `int&&`, which cannot bind to the lvalue `i`, so the guide is not viable. With no viable guide, deduction fails. Clang reports `no viable constructor or deduction guide`.

`T` is a parameter of the class template the constructor belongs to; its type is fixed when `Box<int>` is instantiated, and `Box<int>::Box(int&&)` accepts only rvalues, so CTAD should not deduce anything else. Write a user-defined deduction guide, and the guide's own `T` is a forwarding reference:

```cpp run ok
template<class T> struct Box { Box(T&&) {} };
template<class T> Box(T&&) -> Box<T>;
int main() { int i = 0; Box b(i); (void)b; }   // Box<int&>; the constructor collapses to Box(int&)
```

Example 4 in [[temp.deduct.call#3]] demonstrates the same thing with `A a{i, 0, ip};` and `A a2{i, ip};`.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What are the types of `v2`, `v3` and `v4`?

```cpp run
#include <vector>
std::vector v1{1, 2};
std::vector v2{v1};
std::vector v3{v1, v1};
std::vector v4{v1.begin(), v1.end()};
int main() {}
```

- A. `vector<int>`, `vector<vector<int>>`, `vector<int>`
- B. `vector<int>`, `vector<vector<int>>`, `vector<vector<int>::iterator>`
- C. `vector<vector<int>>`, `vector<vector<int>>`, `vector<int>`
- D. `vector<vector<int>>`, `vector<vector<int>>`, `vector<vector<int>::iterator>`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

CTAD treats deduction guides as constructors of a hypothetical class and performs overload resolution according to the form of initialization ([[over.match.class.deduct#6]]). Brace initialization goes through the two phases of [[over.match.list]]: first only initializer-list constructors, then all constructors.

- `v2{v1}`: item 6.1 of [[over.match.class.deduct#6]] says that if the list has a single element whose type is a specialization of the class template (or derived from one), the first phase is skipped. In the second phase, the copy deduction candidate `vector(vector<T, A>)` (item 1.3) deduces `vector<int>`, and deducing the `initializer_list<T>` parameter from the argument `v1` fails. The result is a copy, not an extra layer of wrapping.
- `v3{v1, v1}`: two elements, so item 6.1 does not apply. In the first phase `vector(initializer_list<T>, ...)` deduces `T = vector<int>`, giving `vector<vector<int>>`.
- `v4{v1.begin(), v1.end()}`: also two elements; in the first phase `initializer_list<T>` deduces `T = vector<int>::iterator` and is viable, so the second phase is never reached, and neither the iterator-pair constructor nor the standard library's iterator deduction guide gets a chance.

To get `vector<int>`, use parentheses: `std::vector v4(v1.begin(), v1.end());`. Then there is only the second phase, and the iterator-range deduction guide is selected.

</details>
</div>

## 4. Concepts and constraints

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

Which statement about `f(1)` and `g(1)` is correct?

```cpp run
#include <concepts>
template<class T> concept Small = sizeof(T) <= 4;
template<class T> concept A = Small<T> && std::integral<T>;
template<class T> concept B = sizeof(T) <= 4 && std::integral<T>;
int f(Small auto) { return 1; }
int f(A auto)     { return 2; }
int g(Small auto) { return 1; }
int g(B auto)     { return 3; }
int main() { return f(1) + g(1); }
```

- A. `f(1)` returns 2 and `g(1)` returns 3
- B. `f(1)` returns 2; `g(1)` is ambiguous and the program is ill-formed
- C. Both `f(1)` and `g(1)` are ambiguous
- D. Both `f(1)` and `g(1)` return 1

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

The two candidates have the same conversion sequences, partial-ordering deduction succeeds in both directions, and the template parameter lists are equivalent (type constraints do not count toward parameter equivalence, [[temp.over.link#6]]), so constraints break the tie: the more constrained template is more specialized ([[temp.func.order#8]], item 8.4). The key is how **subsumption** is decided.

1. Associated constraints are first **normalized** ([[temp.constr.decl#3]]). Normalization expands concepts: the normal form of `Small<T>` is the atomic constraint `sizeof(T) <= 4` in `Small`'s definition ([[temp.constr.normal#1]], item 1.4).
2. Two atomic constraints are **identical** only if they are formed from the **same** expression in the source and have the same parameter mappings ([[temp.constr.atomic#2]]). Subsumption compares only identical atomic constraints ([[temp.constr.order#1]], item 1.2).
3. The normal form of `A<T>` is `sizeof(T) <= 4` (from `Small`'s definition) ∧ the atomic constraints of `std::integral`. It subsumes the normal form of `Small<T>`, so `f(A auto)` is more constrained, and `f(1)` returns 2.
4. The `sizeof(T) <= 4` in `B` is a different place in the source; even though it is spelled the same, it is not identical to the one in `Small`. `B` and `Small` do not subsume each other, the two candidates for `g(1)` cannot be ranked, and the call is ill-formed ([[over.match.best.general#3]]).

After the ambiguity error Clang adds the note `similar constraint expressions not considered equivalent`. Identity is decided by origin only so that compilers do not have to compare arbitrary expressions for equivalence. To reuse a condition and have it take part in subsumption, make it a concept and refer to it by the concept name.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
#include <concepts>
template<class T> concept Big = sizeof(T) > 4;
template<class T> int f(T) requires (!Big<T>) { return 1; }
template<class T> int f(T) requires (!Big<T>) && std::integral<T> { return 2; }
int main() { return f(1); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. Normalization only breaks up `&&`, `||`, parentheses, concept names, and fold expressions over `&&` and `||` ([[temp.constr.normal#1]]). `!Big<T>` is a logical negation expression, none of these, so by item 1.6 it becomes a single atomic constraint as a whole, and `Big` is not expanded inside it.
2. The `!Big<T>` in the two declarations are two expressions in the source, so per [[temp.constr.atomic#2]] they are not identical atomic constraints. The second `f`'s constraint `(!Big<T>)₂ ∧ integral` does not subsume the first's `(!Big<T>)₁` ([[temp.constr.order#1]]).
3. Both `f`s are viable and neither is more constrained, so partial ordering cannot decide ([[temp.func.order#8]], item 8.5); the call is ambiguous and the program is ill-formed ([[over.match.best.general#3]]).

The distractor is "the second one has an extra condition, so of course it is more constrained". Wrap the negation in a concept, and both uses refer to the same atomic constraint in the concept's definition:

```cpp run ok
#include <concepts>
template<class T> concept Big = sizeof(T) > 4;
template<class T> concept NotBig = !Big<T>;
template<class T> int f(T) requires NotBig<T> { return 1; }
template<class T> int f(T) requires NotBig<T> && std::integral<T> { return 2; }
int main() { return f(1); }   // returns 2
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct S { void bar(); };
template<class T> concept HasFoo = requires(T t) { t.foo(); };
static_assert(!HasFoo<S>);
static_assert(!requires(S s) { s.foo(); });
int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. The first `static_assert`: the atomic constraint of `HasFoo<S>` is the *requires-expression*, and `S` is substituted into it when satisfaction is checked ([[temp.constr.atomic#3]]). After substitution `t.foo()` is invalid, and per [[expr.prim.req.general#5]] the *requires-expression* evaluates to `false`; this does not make the program ill-formed. This line holds.
2. The second `static_assert`: the *requires-expression* is not inside any templated entity, so there are no template arguments to substitute. The "evaluates to false" rule applies only to invalid expressions produced by substituting template arguments; here `s.foo()` is just an ordinary expression, `S` has no member `foo`, and by the ordinary rules it is ill-formed. Note 1 in [[expr.prim.req.general#5]] says this explicitly. Clang reports `no member named 'foo' in 'S'`.

A *requires-expression* turns an invalid expression into `false` only when template arguments are substituted. To probe a concrete type in non-template code, go through a concept or template, as the first line does.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
template<class T> requires (sizeof(T)) void f(T) {}
void f(int) {}
int main() { f(0); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. For the call `f(0)`, the function template deduces `T = int`, and then whether the associated constraints are satisfied is checked ([[temp.deduct.general#5]]).
2. Substituting into the atomic constraint `sizeof(T)` produces no invalid type or expression, so it is not "not satisfied". [[temp.constr.atomic#3]] then requires E to be a constant expression of **type bool**, with no contextual conversion; `std::size_t` does not qualify, and the program is ill-formed.
3. The non-template `f(int)` is also an exact match and by item 2.4 of [[over.match.best.general#2]] would have won, but the error occurs while forming the candidate from the template, before any comparison. Example 3 in [[temp.constr.atomic#3]] is the same situation.

Clang reports `atomic constraint must be of type 'bool'` at the template definition, even without a call. Without a call, no well-formed satisfaction check of this atomic constraint is possible and none is ever performed, so the program is IFNDR per item 6.5 of [[temp.res.general#6]], and an early diagnostic is permitted.

Compare with substitution failure: for `requires (T::value)` with `T = int`, substitution makes `int::value` invalid, so the constraint is simply not satisfied, the template is excluded, and the call falls back to other overloads.

```cpp run ok
template<class T> requires (T::value) void g(T) {}
void g(...) {}
int main() { g(0); }   // calls g(...)
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`f(0)` is ambiguous. Explain why, and rewrite `IncDec` without changing its meaning so that `f(0)` selects the second overload.

```cpp run
template<class T> concept Inc    = requires(T t) { ++t; };
template<class T> concept IncDec = requires(T t) { ++t; --t; };
int f(Inc auto)    { return 1; }
int f(IncDec auto) { return 2; }
int main() { return f(0); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Reference answer:** a *requires-expression* as a whole is a single atomic constraint; normalization does not break it up into individual requirements ([[temp.constr.normal#1]], item 1.6; example 2 in [[temp.constr.normal#3]] lists `requires (T x) { ++x; }` as an atomic constraint). `Inc` and `IncDec` each have a single atomic constraint, formed from two different expressions, which are not identical ([[temp.constr.atomic#2]]), so neither subsumes the other. `int` satisfies both, partial ordering cannot decide ([[temp.func.order#8]], item 8.5), and the call is ambiguous.

The compiler does not compare the contents of two *requires-expression*s to see that `{ ++t; }` is a subset of `{ ++t; --t; }`. The fix is to have `IncDec` reuse `Inc` through the concept name:

```cpp run ok
template<class T> concept Inc    = requires(T t) { ++t; };
template<class T> concept IncDec = Inc<T> && requires(T t) { --t; };
int f(Inc auto)    { return 1; }
int f(IncDec auto) { return 2; }
int main() { return f(0); }   // returns 2
```

Now the normal form of `IncDec<T>` is the atomic constraint from `Inc` ∧ the new *requires-expression*, which subsumes `Inc<T>` ([[temp.constr.order#1]]). The set of types satisfying `IncDec` is unchanged. The standard library's concept hierarchy is written this way (for example, `std::bidirectional_iterator` is defined as `std::forward_iterator<I> && ...`). See [[topics/concepts]].

</details>
</div>

## 5. NTTPs, variadics and if constexpr

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct P { int x; mutable int y; };
template<P p> struct B {};
B<P{1, 2}> b;
int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. A constant template parameter must have a **structural type** or a type containing a placeholder ([[temp.param#11]]).
2. For a class type to be structural, all its base classes and non-static data members must be public and non-mutable ([[temp.param#12]], item 12.3.1). `P::y` is mutable, so `P` is not a structural type, and the declaration `template<P p>` is itself ill-formed. Clang reports `type 'P' of non-type template parameter is not a structural type` on that line.

A template parameter object is const, and specializations are distinguished by value ([[temp.param#13]]). A mutable member could be modified on a const object, breaking the premise that "same value means same specialization", so it is excluded.

Remove `mutable` and the program is well-formed. The following are often misjudged as invalid but are all fine: `template<double D>` (floating-point types are scalar types, item 12.1), `template<auto V>` with `'x'`, and `template<const int& R>` with a namespace-scope `constexpr int k`. What is really forbidden is having a reference or pointer refer to objects such as temporaries or string literals ([[temp.arg.nontype#6]]).

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

The four function templates below are called as in `main`. Which of them make the program ill-formed?

```cpp
template<class... T> auto a(T... t) { return (t + ...); }
template<class... T> auto b(T... t) { return (t && ...); }
template<class... T> auto c(T... t) { return (..., t); }
template<class... T> auto d(T... t) { return (0 + ... + t * 2); }
int main() {
  a();
  b();
  c();
  d(1, 2);
}
```

- A. Only `a()`
- B. `a()` and `d`
- C. `a()`, `c()` and `d`
- D. Only `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

- `a()`: when the pack of a unary fold is empty, only `&&`, `||` and `,` have specified values ([[temp.variadic#15]], table 20); for any other operator the instantiation is ill-formed. `+` is not in the table.
- `b()`: an empty `&&` fold yields `true`.
- `c()`: an empty `,` fold yields `void()`. `auto` deduces `void` from `return void();`, and a function returning `void` may return an operand of type `void` ([[stmt.return#2]]), so it is valid.
- `d`: the operands on either side of a fold expression must be *cast-expression*s (the grammar in [[expr.prim.fold#1]]). `t * 2` is a multiplicative expression, not a *cast-expression*, so this is a syntax error, independent of the call's arguments. It should be written `(0 + ... + (t * 2))`.

Those who choose C think an empty comma fold is invalid, or that `auto` cannot deduce `void`. Those who choose A treat `t * 2` as an ordinary expression, but the fold-expression grammar deliberately keeps `+` and `*` from mixing in the operands to avoid precedence ambiguities. Clang reports `expression not permitted as operand of fold expression` for `d`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
#include <type_traits>
int main() {
  int i = 0;
  if constexpr (std::is_pointer_v<decltype(i)>) {
    return *i;
  }
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. The condition is `false`, so the first substatement is a **discarded statement** ([[stmt.if#2]]).
2. But [[stmt.if#2]] only says that a discarded statement is not instantiated when the enclosing templated entity is instantiated. `main` is not a template, there is no instantiation step, and the discarded statement is checked semantically as usual. In non-template code, being discarded means: odr-uses in it do not require the entity to be defined (note 1), and `return` statements in it do not take part in return type deduction ([[dcl.spec.auto.general#4]]).
3. The operand of `*i` must be a pointer ([[expr.unary.op#1]]); `int` is not, and the program is ill-formed.

`if constexpr` is not `#if`. Put it in a template and make the condition depend on a template parameter, and only then is the discarded branch not instantiated:

```cpp run ok
#include <type_traits>
int main() {
  auto get = [](auto v) {
    if constexpr (std::is_pointer_v<decltype(v)>) return *v;
    else return v;
  };
  int i = 0;
  return get(i) + get(&i);
}
```

The function call operator of a generic lambda is a template; when `get(i)` is instantiated, `return *v;` is discarded and not instantiated.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
auto f() {
  if constexpr (true) return 1;
  else return 2.0;
}
int main() { return f() - 1; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; the return type of `f` is `int`.**

1. The definition of a discarded statement ([[stmt.if#2]]) is not limited to templates: when the condition is `true`, the `else` branch is a discarded statement, in a non-template function as well.
2. The return type is deduced from **non-discarded** `return` statements ([[dcl.spec.auto.general#4]]); the rule requiring all deductions to agree also applies only to non-discarded `return` statements ([[dcl.spec.auto.general#10]]). Only `return 1;` takes part in deduction, and the return type is `int`.
3. `return 2.0;` is discarded but must still pass semantic checking (see the previous question). It has no error in itself: `2.0` is a valid expression, it takes no part in deduction, and so it does not conflict with `int`.

This question and the previous one are a pair: a discarded statement in non-template code is still checked, but its `return`s do not take part in deduction. With an ordinary `if`, both `return`s take part in deduction, giving `int` and `double`, and the program is ill-formed:

```cpp error
auto f() {
  if (true) return 1;
  else return 2.0;   // error: 'auto' deduced as double, previously deduced as int
}
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

Both translation units include `f.h`. Judge this program and give the basis, then predict what output you might see on common Itanium ABI implementations (Clang, GCC) when compiling and linking with `-O0` and with `-O2`, and why they differ.

```cpp title="f.h"
template<class T> int f(T) { return 1; }
```

```cpp title="tu1.cpp"
#include <cstdio>
#include "f.h"
int via_tu2();
int main() { std::printf("%d %d\n", f(0), via_tu2()); }
```

```cpp title="tu2.cpp"
#include "f.h"
template<> int f<int>(int) { return 2; }
int via_tu2() { return f(0); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Reference answer: IFNDR.**

`tu1.cpp` calls `f(0)`, which causes an implicit instantiation of `f<int>`, but in that TU no declaration of the explicit specialization of `f<int>` is reachable. [[temp.expl.spec#7]] requires a declaration of an explicit specialization to be reachable, in every TU, from every use that would cause an implicit instantiation; otherwise no diagnostic is required. Neither TU contains a diagnosable error on its own, so the compiler and linker usually report nothing.

In implementation terms, the implicitly instantiated `f<int>` in `tu1.o` is a weak symbol (`weak external` on Mach-O, COMDAT/weak on ELF), while the explicit specialization in `tu2.o` is an ordinary strong symbol with the same mangled name (`_Z1fIiEiT_`). When the linker sees a strong and a weak symbol with the same name, it picks the strong one without complaint.

- `-O0`: the `f(0)` in `tu1` is a real call, which after linking jumps to `tu2`'s explicit specialization, so the output is `2 2`.
- `-O2`: the `f<int>` in `tu1` is inlined to the constant 1 and the symbol is never called, so the output is `1 2`.

That is exactly what we observed with Clang 23: the same source, different optimization levels, different output. This is what IFNDR most often looks like in practice: no diagnostic, and a result that depends on inlining decisions. The fix is to put a declaration of the explicit specialization, `template<> int f<int>(int);`, in `f.h`, so that every use can see it.

</details>
</div>

## Questions and clauses

| No. | Topic | Clauses |
|---|---|---|
| 1 | Members of dependent bases do not take part in lookup at the point of definition | [[temp.res.general#1]], [[class.member.lookup#4]], [[temp.dep.type#3]] |
| 2 | Type-only contexts and where `typename` may be omitted | [[temp.res.general#4]], [[temp.res.general#5]] |
| 3 | `static_assert(false)` and P2593 | [[dcl.pre#13]], [[temp.res.general#6]] |
| 4 | Templates with no valid specialization | [[temp.res.general#6]], [[dcl.array#1]] |
| 5 | Points of instantiation with different meanings | [[temp.point#1]], [[temp.point#7]], [[temp.dep.general#2]] |
| 6 | Ways to call a member of a dependent base | [[temp.dep.type#5]], [[class.member.lookup#4]] |
| 7 | Function-to-pointer decay during deduction | [[temp.deduct.call#2]] |
| 8 | Deduction from braced lists | [[temp.deduct.call#1]], [[temp.deduct.type#5]] |
| 9 | The immediate context of SFINAE | [[temp.deduct.general#8]], [[temp.inst#2]] |
| 10 | Partial ordering of function templates versus conversion sequences | [[temp.deduct.partial#10]], [[over.ics.rank#3]], [[over.match.best.general#2]] |
| 11 | Ambiguous class template partial specializations | [[temp.spec.partial.match#1]], [[temp.spec.partial.order#1]] |
| 12 | Alias templates are transparent in declaration matching | [[temp.alias#2]], [[basic.scope.scope#4]], [[basic.def.odr#2]] |
| 13 | Explicit specializations must be declared before use | [[temp.expl.spec#7]], [[temp.inst#5]] |
| 14 | `T&&` is not a forwarding reference in CTAD | [[temp.deduct.call#3]], [[over.match.class.deduct#1]] |
| 15 | Copy deduction and initializer lists in CTAD | [[over.match.class.deduct#6]], [[over.match.list]] |
| 16 | Identity of atomic constraints, and subsumption | [[temp.constr.normal#1]], [[temp.constr.atomic#2]], [[temp.constr.order#1]] |
| 17 | A negation is an atomic constraint | [[temp.constr.normal#1]], [[temp.func.order#8]] |
| 18 | A *requires-expression* outside a template | [[expr.prim.req.general#5]], [[temp.constr.atomic#3]] |
| 19 | Atomic constraints must be of type bool | [[temp.constr.atomic#3]], [[temp.deduct.general#5]] |
| 20 | A *requires-expression* as a whole is one atomic constraint | [[temp.constr.normal#1]], [[temp.constr.order#1]] |
| 21 | Structural types | [[temp.param#11]], [[temp.param#12]] |
| 22 | Empty-pack folds and the grammar of fold expressions | [[temp.variadic#15]], [[expr.prim.fold#1]] |
| 23 | Discarded statements in non-template code are still checked | [[stmt.if#2]], [[expr.unary.op#1]] |
| 24 | `return` in a discarded statement does not take part in deduction | [[dcl.spec.auto.general#4]], [[dcl.spec.auto.general#10]] |
| 25 | Explicit specialization across TUs | [[temp.expl.spec#7]] |
