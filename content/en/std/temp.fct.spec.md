---
title: Function template specializations
summary: "When a function template is called or referenced, its template arguments come from three sources: written explicitly, deduced from the arguments, or defaulted; where explicit template arguments can be written, which can be omitted, what an empty f<>() is for, and why explicit specification lets arguments undergo implicit conversions."
updated: 2026-10-19
---

!!! tldr
    - Every template argument of a function template needs a value, from one of three sources: written explicitly (`f<int>(x)`), deduced from the call arguments, or taken from a default template argument. The three can be mixed.
    - Explicit arguments fill the template parameters in declaration order, and only trailing ones that can be deduced or have defaults can be omitted. So parameters that need to be specified explicitly should come first.
    - An explicitly specified template parameter no longer takes part in deduction, so the corresponding function arguments can undergo ordinary implicit conversions: `max_(1, 2.5)` has a deduction conflict, while `max_<double>(1, 2.5)` compiles.
    - An empty `f<>(x)` means only templates are considered, excluding a non-template function with the same name.
    - A constructor template can't be given explicit template arguments; its template arguments can only be deduced or defaulted.

## Where template arguments come from ([temp.fct.spec.general])

```cpp
template<class U, class V> U convert(V v);

int i = convert<int>(3.14);   // U written explicitly, V deduced from the argument as double
```

¶1 A function instantiated from a function template is called a [[g:function-template-specialization|**function template specialization**]]; so is an explicit specialization of a function template ([[temp.expl.spec]]). Determining a specialization requires all its template arguments, which can be:

1. written explicitly when naming the specialization, like `<int>` above;
2. deduced from the context, most commonly from the call arguments ([[temp.deduct]]);
3. taken from default template arguments, like `A` in `template<class T, class A = std::allocator<T>>`.

`convert<int>(3.14)` uses the first two at once. How the three combine is covered under ¶4 below and in [[temp.deduct.general#5]].

¶2 Each instantiated specialization has its own copy of any static variables:

```cpp run ok
template<class T> int counter(T*) {
    static int n = 0;
    return ++n;
}

int main() {
    int a; char* b;
    counter(&a); counter(&a);   // counter<int>: n == 2
    counter(&b);                // counter<char*>: n == 1
    return counter(&a) == 3 && counter(&b) == 2 ? 0 : 1;   // returns 0
}
```

`counter<int>` and `counter<char*>` are two different functions, just as static members of a class template exist once per specialization ([[temp.spec#7]]). `f<int>` and `f<const int>` have the same function type (top-level `const` on parameters is dropped), but they are still two specializations, each with its own static variables ([[temp.deduct.general#4]]).

## Writing template arguments explicitly ([temp.arg.explicit])

### When they must be written (¶1)

¶1 When naming a function template specialization, a template argument list can be written after the name, as for class templates:

```cpp ok
template<class T> struct Array { };
template<class T> void sort(Array<T>& v);
template<class U, class V> U convert(V v);

void f(Array<double>& cv, Array<int>& ci, double d) {
    sort<double>(cv);                  // sort(Array<double>&)
    sort<int>(ci);                     // sort(Array<int>&)
    int  i = convert<int, double>(d);  // int convert(double)
    char c = convert<char, double>(d); // char convert(double)
    (void)i; (void)c;
}
```

The arguments of `sort` can all be deduced, so writing them is optional. The `U` of `convert` appears only in the return type and can't be deduced from the call arguments (Note 1 of [[temp.deduct.call#5]]), so it must be written. `std::make_unique<T>(args...)` and `std::get<I>(t)` are both in this category.

### Where they can be written (¶3)

¶3 A template argument list for a function template specialization can appear:

- ¶3.1 when calling the function: `f<int>(x)`;
- ¶3.2 when taking the address of a function, initializing a reference to function with it, or forming a pointer to member function: `&f<int>`, `void (&r)(int) = f<int>;`, `&X::mf<int>`;
- ¶3.3 in an explicit specialization: `template<> void f<int>(int);`;
- ¶3.4 in an explicit instantiation: `template void f<int>(int);`;
- ¶3.5 in a friend declaration: `friend void f<int>(int);`.

!!! note "`template` in dependent contexts"
    Inside a template, if the object to the left of `.` or `->`, or the qualifier to the left of `::`, depends on a template parameter, the `template` keyword is needed to say that the following `<` starts a template argument list: `t.template get<0>()`, `T::template make<int>()` ([[temp.names]]).

### Filled in order; trailing ones can be omitted (¶4, ¶6)

¶6 Explicit template arguments are listed in the order of the corresponding template parameters. There can't be more of them than there are template parameters, unless one of them is a template parameter pack ([[temp.variadic]]).

¶4 Trailing template arguments that can be deduced or have defaults can be omitted. Note 1 adds that a trailing template parameter pack not otherwise deduced is deduced as empty. If all template arguments can be obtained this way, none need be written, and then even the empty `<>` can be omitted.

```cpp ok
template<class X, class Y, class Z> X f(Y, Z);
template<class... Args> void f2();

void g() {
    f<int, const char*, double>("aa", 3.0);
    f<int, const char*>("aa", 3.0);    // Z deduced as double
    f<int>("aa", 3.0);                 // Y and Z both deduced
    f2<char, short, int, long>();      // all four go into the pack Args
}
```

```cpp error
template<class X, class Y, class Z> X f(Y, Z);
void g() { f("aa", 3.0); }             // error: X can't be deduced
```

So when designing function templates, put parameters that need explicit specification first and deducible ones after. `std::make_unique<T, Args...>` has exactly this order. Written the other way round, as `template<class Y, class X> X f(Y)`, users would have to write `f<double, int>(5.6)`, spelling out the deducible `Y` as well.

Example 2 in the standard has a subtler case, where the argument is itself the name of another function template:

```cpp
template<class X, class Y> X f(Y);
template<class X, class Y, class... Z> X g(Y);

void h() {
    f<void>(f<int, bool>);     // OK: the outer f's Y is deduced as int(*)(bool)
    f<void>(f<int>);           // error: f<int> isn't a unique specialization
    f<void>(g<int, bool>);     // OK: g's pack Z is deduced as empty
}
```

- `f<int>` fixes only `X`; `Y` is still unknown, so it stands for infinitely many possible specializations and is an overload set. Deducing from an overload set containing a function template is a non-deduced context ([[temp.deduct.call#6]]), so the outer `Y` can't be deduced.
- In `g<int, bool>`, the trailing pack `Z` is deduced as empty per Note 1, so it designates the unique specialization `int g<int, bool>(bool)`, and the outer call can deduce.

### `f<>(x)`: templates only (¶5)

```cpp run ok
#include <cstdio>
template <class T> int f(T) { return 1; }   // #1
int f(int) { return 2; }                    // #2

int main() {
    std::printf("%d %d\n", f(1), f<>(1));   // prints 2 1
}
```

¶5 Note 2 points out that an empty template argument list can be used to say that a function template specialization is wanted here, even if a non-template function that would otherwise be selected is visible. For `f(1)` the two candidates are equally good, and [[over.match.best]] ¶2.4 makes the non-template win; `f<>(1)` has a template argument list, so the non-template function isn't even a candidate.

### Explicitly specified parameters allow implicit conversions (¶7)

<div class="compare" markdown="1">

```cpp error
template<class T>
T max_(T a, T b) { return a < b ? b : a; }

// T deduced as int and as double: conflict
double m = max_(1, 2.5);    // error
```

```cpp ok
template<class T>
T max_(T a, T b) { return a < b ? b : a; }

// T no longer deduced, 1 converted to double
double m = max_<double>(1, 2.5);
```

</div>

During deduction, only a few kinds of difference between argument and parameter types are allowed ([[temp.deduct.call#4]]), and a conversion like `int` to `double` isn't one of them.

¶7 says that if a function parameter's type contains no template parameters that participate in deduction, the corresponding argument undergoes ordinary implicit conversion ([[conv]]). Note 3 explains that explicitly specified template parameters don't participate in deduction. So once you write `max_<double>`, it's an ordinary `double max_(double, double)`, and arguments are converted as usual. The conversion can be user-defined, too:

```cpp ok
template<class T> void f(T);
class Complex { public: Complex(double); };

void g() {
    f<Complex>(1);    // OK: equivalent to f<Complex>(Complex(1))
}
```

Since C++20, `std::type_identity_t<T>` can also be used to put a parameter into a non-deduced context, deducing `T` only from the other parameters and letting that parameter accept conversions (see [[temp.deduct.type]]).

### Deduction can keep extending a pack (¶9)

```cpp ok
#include <type_traits>
template<class... Types> void f(Types... values) {
    static_assert(std::is_same_v<void(Types...), void(int*, float*, int)>);
    (void)sizeof...(values);
}

void g() {
    f<int*, float*>(0, 0, 0);   // Types is int*, float*, int
}
```

¶9 Even when a template parameter pack has explicitly specified arguments, deduction can still append more. In the example, the first two `0`s correspond to the explicitly written `int*` and `float*` and are converted as null pointer constants; the third `0` is beyond the explicit part, and deduction adds `int`. Writing a few elements of a pack explicitly just fixes its prefix.

If the pack isn't at the end, all the explicit arguments go into the pack, and later parameters can only be deduced:

```cpp ok
#include <type_traits>
template<class... Ts, class U> void f(U) {
    static_assert(sizeof...(Ts) == 2);
    static_assert(std::is_same_v<U, double>);
}
void g() { f<int, char>(1.0); }   // Ts = {int, char}, U deduced from the argument
```

### Constructor templates can't be explicitly specified (¶2, ¶8)

¶2 Template arguments can't be specified when naming a specialization of a constructor template. Note 4 under ¶8 explains why: an explicit template argument list has to follow the function template's name, and constructors have no name that can be used this way (`X::X` names the class, [[class.qual]]).

```cpp
struct S { template<class T> S(T); };
S s = S<int>(1);    // error: S isn't a template; this doesn't specify T for the constructor
```

So the template arguments of a constructor template can only be deduced or defaulted. When the caller needs to specify a type, the idiom is a tag parameter such as `std::in_place_type_t<T>`:

```cpp ok
#include <utility>
struct Any {
    template<class T, class... Args>
    explicit Any(std::in_place_type_t<T>, Args&&...) { }
};
Any a(std::in_place_type<int>, 42);   // T deduced as int from the tag's type
```

## Common misconceptions

!!! pitfall "Writing `g<int>(i)` for a forwarding reference"
    The special rule for forwarding references (an lvalue argument makes `T` deduce as an lvalue reference) only applies during deduction. For `template<class T> void g(T&&)`, writing `g<int>(i)` fixes `T` as `int`, the parameter is `int&&`, which can't bind the lvalue `i`, and the call fails. `std::forward<T>(x)` turns this around: its parameter is a non-deduced context, forcing the caller to write `T`.

!!! pitfall "An invalid explicit argument causes a hard error"
    It doesn't. Explicit arguments are first substituted into the function type ([[temp.deduct.general#2]]), and if that gives an invalid type, deduction just fails and the template is quietly removed. For `template<class T> void f(typename T::type)`, writing `f<int>(0)` with no other candidates reports that there is no matching function, not that `int` has no member `type`.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> void f(T, T);
    void g(long l) {
        f(1, l);         // (a)
        f<long>(1, l);   // (b)
        f<>(1, l);       // (c)
    }
    ```
    Which are well-formed?

<details markdown="1">
<summary>Answer</summary>

Only (b). (a): `T` is deduced as `int` from the first argument and as `long` from the second, a conflict. (b): `T` is explicitly specified as `long` and doesn't participate in deduction, and `1` is implicitly converted to `long` (¶7). (c): `<>` specifies no arguments, `T` still has to be deduced, same as (a). Clang 23 agrees.
</details>

!!! question "Question 2"
    Why does `std::make_shared<int>(42)` compile but `std::make_shared(42)` not? What would happen if it were declared `template<class... Args, class T> shared_ptr<T> make_shared(Args&&...)`?

<details markdown="1">
<summary>Answer</summary>

`make_shared` is declared `template<class T, class... Args> shared_ptr<T> make_shared(Args&&... args);`. `T` appears only in the return type and can't be deduced, so `make_shared(42)` fails; in `make_shared<int>(42)`, `T = int` and `Args` is deduced as `int`.

With the pack first, an explicitly written `int` would go into `Args` (¶6, ¶9), and `T` could neither be deduced nor written, so the function template couldn't be called unless `T` had a default. That's why parameters needing explicit specification should come first.
</details>
