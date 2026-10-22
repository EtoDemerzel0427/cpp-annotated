---
title: Deduced class template specialization types
summary: "Where the argument-less template name in std::pair p(1, 2.0) can appear: initializing declarations of variables (declared type only cv T), new expressions, functional casts and template parameters; multiple declarators must deduce the same type."
updated: 2026-10-19
---

!!! tldr
    - In `std::pair p(1, 2.0);`, `std::pair` is a placeholder for a deduced class type, and the compiler deduces `std::pair<int, double>` from the initializer. This is called class template argument deduction (CTAD).
    - For a variable, the declared type can only be `cv T`: no `const std::pair&`, no `std::pair*`, and no arrays.
    - Beyond that it can only be used in `new`, a functional cast `std::pair(1, 2)`, and template parameters; function parameters, return types and non-static data members are all out.
    - CTAD is all or nothing: once `<…>` is written, it is an ordinary template specialization and the remaining arguments aren't deduced.
    - With a single element that is itself a specialization of this template, CTAD chooses copying: `std::vector v2{v1};` is `vector<int>`, not `vector<vector<int>>`.

**Class template argument deduction** (CTAD, C++17, [[P0091R3]]) lets us omit a class template's arguments and deduce them from the initializer. A template name with its arguments omitted is a **placeholder for a deduced class type** ([[g:deduced-class-type-placeholder]]); which names count as placeholders is specified by [[dcl.type.simple#3]]. The deduction algorithm is specified by [[over.match.class.deduct]]: it synthesizes a set of fictional function templates from the constructors and deduction guides ([[temp.deduct.guide]]) and then performs overload resolution. This subclause only specifies where the placeholder can appear and what it is finally replaced by.

## Variables: the declared type can only be cv T (¶1)

<div class="compare" markdown="1">

```cpp run ok
#include <utility>
std::pair p(1, 2.0);
const std::pair cp(1, 'c');
std::pair a(1, 2), b(3, 4);
int main() {
  return cp.first + a.first - 2;
}
```

```cpp error
#include <utility>
const std::pair& r{1, 2};  // error
std::pair* q = nullptr;    // error
std::pair arr[2]{};        // error
int main() {}
```

</div>

¶1 If a placeholder for a deduced class type appears as a specifier in an initializing declaration of a variable ([[dcl.init]]), the declared type of the variable must be `cv T`, where T is the placeholder. The declarator can't contain modifiers such as `&`, `*` or `[]`. The placeholder is replaced by the return type of the function selected by overload resolution.

`auto` allows `const auto&` and `auto*`, because `auto` deduction is template argument deduction, and patterns like `const U&` and `U*` match naturally. CTAD deduction, however, is overload resolution over constructors; it answers the question of what type of object is being constructed here. Does `std::pair* q = …` construct `*q` or something else? `const std::pair& r{1, 2}` constructs a temporary. There's no obviously correct meaning for CTAD on references, pointers or arrays, so the standard only allows `cv T`.

The last sentence of ¶1 says that if a declaration has multiple declarators, the type replacing the placeholder must be the same each time:

```cpp error
#include <utility>
std::pair a(1, 2), b(3, 4.0);   // error: pair<int, int> vs pair<int, double>
```

The initializing-declaration requirement means all template parameters must be deducible from the initializer. `std::pair p;` performs default-initialization, but the default constructor can't deduce `T1` and `T2`, so it is ill-formed. If all template parameters of a class template have default arguments, as in `template<class T = int> struct D { };`, then `D d;` is valid CTAD.

### No partial deduction

Once `<…>` is written, it is no longer a placeholder but an ordinary template specialization, and all template arguments without defaults must be given:

```cpp error
#include <utility>
std::pair<int> p(1, 2);   // error: too few template arguments; the rest aren't deduced
```

This is intentional. If partial deduction were allowed, then after a class template with default template arguments gained a new parameter, the type of existing code such as `std::tuple<int> t(1, 2.0)` could silently change.

## Other permitted positions (¶2)

¶2 A placeholder for a deduced class type can also be used in three other places:

- in the type of a `new` expression ([[expr.new]]): `new std::pair(1, 2)`;
- in an explicit type conversion in functional notation ([[expr.type.conv]]): `std::pair(1, 2)`, `std::vector{1, 2}`;
- in the type of a template parameter ([[temp.param]]): `template<Box B> struct K;`, where the type of the constant template parameter is deduced from the template argument (C++20).

Appearing anywhere else is ill-formed.

```cpp run ok
#include <utility>
template<class T> struct Box { T v; };
template<Box B> struct K { static constexpr auto value = B.v; };
int main() {
    auto* np = new std::pair(1, 2);         // new expression
    auto fc = std::pair(3, 4.0);            // functional cast
    static_assert(K<Box{5}>::value == 5);   // template parameter; Box{5} is itself CTAD
    int r = np->first + fc.first - 4;
    delete np;
    return r;
}
```

<div class="compare" markdown="1">

```cpp error
#include <utility>
void f(std::pair p);   // error
std::pair g();         // error
struct S {
  std::pair p{1, 2};   // error
};
```

```cpp run ok
#include <utility>
struct S {
  // a static data member is a variable
  static inline std::pair
      p{1, 2};
};
int main() {}
```

</div>

Named casts like `static_cast<std::pair>(…)` don't work either. Function parameters can't use a CTAD placeholder because that would require turning the function into a template, and the semantics of CTAD, deducing from constructor arguments, differ from deducing parameter types from function call arguments. C++20 abbreviated function templates `void f(auto p)` with concept constraints largely meet this need.

## Outline of the deduction process

This subclause only says that the placeholder is replaced by the return type of the selected function; the algorithm is in [[over.match.class.deduct]]. Roughly:

1. For each constructor of the class template, synthesize a fictional function template whose template parameters are the class template's parameters plus the constructor's own template parameters, and whose return type is a specialization of the class template. If the class declares no constructors, use a hypothetical default constructor.
2. Add the **copy deduction candidate**, equivalent to `template<class T> A(A<T>) -> A<T>;`.
3. Add the user-written deduction guides.
4. If the class is an aggregate, add the aggregate deduction candidate (C++20, [[P1816R0]]).
5. Perform overload resolution over these candidates with the initializer; the return type of the selected candidate is the deduction result.

The standard's example in ¶3:

```cpp error
#include <vector>
#include <iterator>
template<class T> struct container {
    container(T t) { }
    template<class Iter> container(Iter beg, Iter end);
};
template<class Iter>
container(Iter b, Iter e) -> container<typename std::iterator_traits<Iter>::value_type>;
std::vector<double> v = { /* ... */ };

container c(7);                           // OK: T = int
auto d = container(v.begin(), v.end());   // OK: the deduction guide gives container<double>
container e{5, 6};                        // error: int is not an iterator
```

When deducing `e`, the candidate synthesized from `container(Iter, Iter)` can't deduce `T` (`T` doesn't appear in the parameters) and is discarded; the deduction guide participates with `Iter = int`, substitution of `iterator_traits<int>::value_type` fails, and it is discarded too; the remaining candidates accept only one argument. There is no viable candidate, so it is ill-formed.

### Copying is preferred for a single element

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v1{1, 2};
std::vector v2{v1};       // copy: std::vector<int>
std::vector v3{v1, v1};   // two elements: std::vector<std::vector<int>>
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() {}
```

When the braces contain a single element whose type is a specialization of this template (or a class derived from one), item 6.1 of [[over.match.class.deduct#6]] skips the phase of list-initialization that considers initializer-list constructors, so the copy deduction candidate wins; all else being equal, it is also better than ordinary candidates (item 2.12 of [[over.match.best]]). In generic code this can be surprising: if `x` is itself a `std::tuple`, the type of `t` in `std::tuple t{x};` is the type of `x`, not a nested tuple.

## Comparison with auto

| | `auto x = e;` | `std::pair x(a, b);` |
|---|---|---|
| Basis for deduction | The type of the initializer (template argument deduction) | Constructors and deduction guides (overload resolution) |
| `const`, `&`, `*` | `const auto&` and `auto*` allowed | Only `cv T` allowed |
| Resulting type | Anything | Some specialization of this template |
| Function parameters | `void f(auto)` makes the function a template | Not allowed |
| Return types | Allowed | Not allowed |

## Implementation notes

!!! impl "Diagnostics and warnings"
    - For `W w5(1), *pw = nullptr;`, Clang 23 reports "cannot form pointer to deduced class template specialization type".
    - CTAD doesn't affect the ABI. After deduction the variable's type is an ordinary class template specialization, leaving no trace in mangled names.
    - Clang's `-Wctad-maybe-unsupported` warns when a class template with no user deduction guides is used for CTAD, since its author may not have considered CTAD behavior. Once the class author declares any deduction guide, the warning no longer fires.

## History

!!! history
    - C++17 introduced CTAD ([[P0091R3]]), usable for variables, `new` and functional casts.
    - C++20 added CTAD for alias templates ([[P1814R0]], see deducible templates in [[dcl.type.simple#3]]) and for aggregates ([[P1816R0]]), and allowed declaring constant template parameters of class type with a placeholder (`template<Box B>`).
    - C++23 allowed deduction from inherited constructors.
    - C++26 allows a splice `[: r :]` designating a class template as a placeholder (item 3.3 of [[dcl.type.simple#3]]).

## Common misconceptions

!!! pitfall "With CTAD there's no need for `make_pair`"
    Mostly true, but `std::make_pair` unwraps `std::reference_wrapper<T>` into `T&`, while CTAD for `std::pair` doesn't: the deduced member type is still `reference_wrapper`.

## Questions

!!! question "Question"
    Which of the following declarations are well-formed?

    ```cpp
    template<class T> struct W { W(T) { } };
    W w1 = 1;
    W w2(1), w3(2u);
    const W w4{1.0};
    W w5(1), *pw = nullptr;
    W<int> w6 = W(1);
    ```

<details markdown="1">
<summary>Answer</summary>

- `w1`: well-formed, `W<int>`.
- `w2(1), w3(2u)`: ill-formed. `w2` deduces `W<int>` and `w3` deduces `W<unsigned>`, which differ (¶1).
- `w4`: well-formed, `const W<double>`; `cv T` is allowed.
- `w5(1), *pw = nullptr`: ill-formed. The second declarator is a pointer, so its declared type isn't `cv T`; ¶1 applies to every declarator.
- `w6`: well-formed. `W<int>` is an ordinary type, and `W(1)` is CTAD in a functional cast (¶2), giving a prvalue of `W<int>`.
</details>
