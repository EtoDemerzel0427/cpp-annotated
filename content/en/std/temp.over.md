---
title: Overload resolution with function templates
summary: "How function templates take part in overload resolution: for each call, deduction is done for every template; on success a specialization's declaration is synthesized and added to the candidate set, on failure nothing is added, which is why SFINAE isn't an error; then conversion sequences are compared first, a non-template wins when they're equally good, and after that the more specialized template."
updated: 2026-10-19
---

!!! tldr
    - For every call, template argument deduction is done for each function template; on success, the declaration of a concrete specialization is synthesized and added to the candidate set like an ordinary function.
    - If deduction fails or the synthesized declaration would be ill-formed, the template contributes no candidate, and there's no error. This is where SFINAE not being an error comes from.
    - Arguments that take part in deduction only allow a few kinds of conversion; parameters that don't take part in deduction allow any implicit conversion as usual.
    - When comparing candidates, conversion sequences come first; only when they're indistinguishable do the non-template preference and the more-specialized-template preference apply.
    - Only declarations are synthesized; function bodies aren't instantiated, so overload resolution works even if the template is only declared, not defined.

## Templates whose deduction fails don't take part (¶1–¶2)

```cpp error
template<class T> T max(T a, T b) { return a > b ? a : b; }

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // max<int>
    char m2 = max(c, d);    // max<char>
    int m3 = max(a, c);     // error: can't generate max(int, char)
}
```

`max(a, c)` deduces `T = int` from the first argument and `T = char` from the second, a conflict, so deduction fails. The template contributes no candidate, the candidate set is empty, and an error is reported. Adding a non-template function catches this call:

```cpp ok
template<class T> T max(T a, T b) { return a > b ? a : b; }
int max(int, int);

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // max<int> and max(int,int) equally good; the non-template wins
    char m2 = max(c, d);    // max<char> is an exact match, better than max(int,int), which needs promotions
    int m3 = max(a, c);     // only max(int,int): c is promoted to int
    (void)m1; (void)m2; (void)m3;
}
```

¶1 When a call to a function is written (including implicitly, using operator notation), template argument deduction ([[temp.deduct]]) and checking of any explicit template arguments ([[temp.arg]]) are performed for each function template, to find template arguments with which the instantiated specialization can be called with the call's arguments. For conversion function templates, the goal is to find ones that can convert to the required type. Then:

- ¶1.1 if deduction and checking succeed, the resulting template arguments are used to synthesize the declaration of a specialization, which is added to the candidate set;
- ¶1.2 if deduction fails, or the synthesized specialization would be ill-formed, no function from that template is added to the candidate set.

The candidate set consists of all synthesized declarations and all non-template functions found by name lookup. From then on, synthesized declarations take part in overload resolution like any other function, except where [[over.match.best]] says otherwise.

!!! std
    If the argument deduction fails or the synthesized function template specialization would be ill-formed, no such function is added to the set of candidate functions for that template.

[[temp.deduct.general#8]] says substitution failure causes deduction failure, and ¶1.2 says a template whose deduction fails isn't added to the candidates; together they make SFINAE (substitution failure is not an error): the failing template quietly disappears. Only when all candidates have disappeared or none is viable is "no matching function" reported.

¶1 only synthesizes declarations. The function body is instantiated only once the specialization is selected and used ([[temp.inst#11]]), so errors in the body aren't covered by SFINAE:

<div class="compare" markdown="1">

```cpp error
template<class T>
auto size_of(const T& c) {
  return c.size();
}
int size_of(...);
int n = size_of(42);
// error: the template is selected, its body
// instantiated, and int has no size()
```

```cpp ok
template<class T>
auto size_of(const T& c)
    -> decltype(c.size()) {
  return c.size();
}
int size_of(...);
int n = size_of(42);
// OK: deduction fails, size_of(...) selected
```

</div>

The template signature on the left is fine, deduction succeeds, and it's better than the ellipsis version, so it's selected; then the body is instantiated and `c.size()` fails, a hard error. The right side writes `c.size()` into the signature, so substitution fails and the template drops out of the candidate set.

## Conversions allowed in deduction (¶3–¶4)

Arguments that take part in deduction only allow the few conversions listed in [[temp.deduct.call#4]], such as derived to base:

```cpp ok
template<class T> struct B { };
template<class T> struct D : public B<T> { };
template<class T> void f(B<T>&) { }

void g(B<int>& bi, D<int>& di) {
    f(bi);    // T = int
    f(di);    // T = int, D<int>& converted to B<int>&
}
```

Parts of parameters that contain no template parameters don't take part in deduction, and their arguments can undergo any implicit conversion:

```cpp run ok title="nondeduced_conv.cpp"
#include <cstdio>
template<class T> void f(T*, int)  { std::puts("#1"); }
template<class T> void f(T, char)  { std::puts("#2"); }

int main() {
    int* pi = nullptr; int i = 0; char c = 0;
    f(pi, i);   // #1: f<int>(pi, i)
    f(pi, c);   // #2: f<int*>(pi, c)
    f(i, c);    // #2: f<int>(i, c)
    f(i, i);    // #2: f<int>(i, char(i))
}
```

- `f(pi, i)`: both arguments of #1 are exact matches; #2 is `f<int*>(int*, char)`, and the second argument needs a conversion from `int` to `char`. #1 wins.
- `f(pi, c)`: #1's second argument needs a promotion; #2 is all exact matches. #2 wins.
- `f(i, c)` and `f(i, i)`: #1 fails deduction (`T*` can't match `int`), leaving only #2. In `f(i, i)` the second parameter `char` doesn't take part in deduction, so the conversion from `int` to `char` is allowed as usual.

The footnote to ¶1 explains this design: for specializations produced by deduction, parameters either match the arguments exactly or differ only by those few limited conversions; non-deduced parameters allow all conversions.

## Breaking ties

Once synthesized candidates enter [[over.match.best]], their implicit conversion sequences are compared first, like any other candidate's. Only when the conversion sequences are indistinguishable are the following used, in order:

1. ¶2.4: a non-template function is better than a function template specialization;
2. ¶2.5: if both are template specializations, the more specialized template by partial ordering ([[temp.func.order]]) wins;
3. after that come further rules such as comparison by constraints.

The order is what matters: an exactly matching template specialization beats a non-template function that needs a conversion.

```cpp run ok title="template_vs_nontemplate.cpp"
#include <cstdio>
template<class T> void g(T) { std::puts("template"); }
void g(int)                 { std::puts("non-template int"); }
void g(long)                { std::puts("non-template long"); }

int main() {
    g(1);      // non-template int: as good as g<int>, the non-template wins
    g('a');    // template: g<char> is an exact match, better than g(int), which needs a promotion
    g(1L);     // non-template long
    g(1u);     // template: g<unsigned> is an exact match; both non-templates need conversions
}
```

A common surprise is writing an overload for strings and having calls go to the template:

```cpp run ok title="string_overload.cpp"
#include <cstdio>
#include <string>
void show(const std::string&) { std::puts("string"); }
template<class T> void show(const T&) { std::puts("template"); }

int main() {
    show("hi");               // template: T = char[3], exact match; the string version needs a user-defined conversion
    show(std::string("hi"));  // string: equally good, the non-template wins
}
```

A string literal isn't a `std::string`. The fix is to add a `show(const char*)` overload, or to constrain the template.

## Only a declaration is needed (¶5)

```cpp
template<class T> void f(T);    // declaration only

void g() {
    f("Annemarie");             // calls f<const char*>
}
```

¶5 Adding a specialization to the candidate set only needs its signature, so only the template's declaration has to be visible at the call. This call is well-formed; but the program also requires some translation unit to explicitly instantiate `f<const char*>` ([[temp.explicit]]), or it is ill-formed ([[temp.pre]]). This is what allows putting template definitions in a `.cpp` file and explicitly instantiating the specializations needed.

Under a no matching function error, Clang and GCC list each template removed by ¶1.2 as a note with the reason, for example candidate template ignored: deduced conflicting types for parameter 'T'. This is the most useful information when debugging SFINAE.

## Common misconceptions

!!! pitfall "The perfect-forwarding constructor steals the copy"
    ```cpp
    struct Person {
        template<class S> Person(S&& name);   // forwarding constructor
        Person(const Person&);                // copy constructor
    };
    Person p("x");
    Person q(p);    // calls the template
    ```
    `p` is a non-const lvalue, so the template deduces `Person(Person&)`, an exact match; the copy constructor needs `const` added. The conversion sequences already decide, so the non-template preference never applies. Exclude `Person` itself with a constraint: `requires (!std::is_same_v<std::remove_cvref_t<S>, Person>)`.

!!! pitfall "If there's a non-template function, it's always chosen"
    The non-template preference is only a tie-breaker for indistinguishable conversion sequences; see `g('a')` above.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> void f(T, T);
    void f(double, double);
    f(1, 2.0);
    f(1, 2);
    ```
    Which function does each call select?

<details markdown="1">
<summary>Answer</summary>

`f(1, 2.0)`: deducing the template gives conflicting `T` (`int` and `double`), so it contributes no candidate; the non-template `f(double, double)` is viable. The non-template is called.

`f(1, 2)`: the template synthesizes `f<int>(int, int)`, an exact match; the non-template needs two conversions from `int` to `double`. `f<int>` is called.
</details>

!!! question "Question 2"
    Why does ¶1.2 say "the synthesized specialization would be ill-formed" in addition to deduction failing?

<details markdown="1">
<summary>Answer</summary>

Deduction ([[temp.deduct]]) already counts an invalid type after substitution as deduction failure. The second condition covers checks outside deduction, such as explicit template arguments of the wrong kind or too many of them for the template parameters ([[temp.arg]]). The sentence guarantees that any template that runs into trouble while forming the candidate declaration is simply discarded, rather than making the whole call ill-formed.
</details>
