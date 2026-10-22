---
title: Expansion statements (template for)
summary: "C++26's template for is not a loop: it replicates the loop body into several independent instantiations, one per element, for iterating over parameter packs, tuples, the members of aggregates and compile-time ranges."
updated: 2026-10-19
---

!!! tldr
    - `template for` replicates the loop body N times at compile time, each copy a separate instantiation, so the loop variable can have a different type in each copy.
    - When the initializer is a `{...}` list, it expands expression by expression (enumerating); when it is a compile-time iterable range, it expands by iterator (iterating); otherwise it is taken apart by structured binding (destructuring), which is the path for arrays, `std::tuple` and aggregates.
    - The loop body must be a compound statement; it cannot be jumped into from outside and cannot contain labels; `break`, `continue` and `return` can jump out of it.
    - The loop body is treated as a template definition, so `if constexpr` can discard branches by element type in the body even when the enclosing function is not a template.
    - `break` affects only execution, not instantiation: all N copies of the body are instantiated.

{{c++26}} The [[g:expansion-statement|expansion statement]] `template for` was introduced by [[P1306R5]]. It looks much like range-based for, but it is not an iteration statement: it walks at compile time over a group of things whose types may all differ, generating one copy of the loop body per element.

<div class="compare" markdown="1">

```cpp ok
#include <cstdio>
#include <tuple>
// C++17: apply + fold expression
void print17(const auto& t) {
  std::apply([](const auto&... xs) {
    ((std::printf("%d\n", (int)xs)), ...);
  }, t);
}
```

```cpp run ok
#include <cstdio>
#include <tuple>
// C++26: expansion statement
void print26(const auto& t) {
  template for (const auto& x : t)
  {
    std::printf("%d\n", (int)x);
  }
}
int main() {
  print26(std::tuple{1, 'c', 2.5});
}
```

</div>

The right side prints `1`, `99`, `2`. In the three copies of the loop body, the type of `x` is `const int&`, `const char&` and `const double&` in turn.

## Syntax and restrictions

¶1 The syntax of an expansion statement is:

```text
template for ( init-statement(opt) for-range-declaration : expansion-initializer ) compound-statement

expansion-initializer:
    expression
    { expression-list ,(opt) }
    { }
```

The loop body must be a compound statement. Clang 23 accepts a body without braces, but under `-pedantic` warns that ISO C++ requires a compound statement.

The braced form is called an *expansion-init-list*, and it is not an ordinary braced initializer list: `{a, b, c}` is not deduced as a `std::initializer_list` but is several independent expressions, whose types can differ. In range-based for, `for (int x : {1, 2, 3})` requires all elements to have the same type.

¶2 The loop body is a [[g:control-flow-limited-statement|control-flow-limited statement]] ([[stmt.label#3]]): it cannot be entered from outside by `goto`, and `case` labels of an outer `switch` cannot appear in it. In addition, [[stmt.label#4]] says an expansion statement cannot contain identifier labels, because the loop body is replicated N times and the same label would be defined N times.

<div class="compare" markdown="1">

```cpp error
void f() {
  template for (auto x : {1}) {
    (void)x;
  in:;   // error: no labels allowed
  }
}
```

```cpp ok
int f(int k) {
  int r = 0;
  template for (auto x : {1, 2, 3}) {
    if (x == k) goto out;  // OK: jumping out
    r += x;
  }
out:
  return r;
}
```

</div>

## Three ways of expanding

¶4 Which kind an expansion statement is, is decided in this order:

| Kind | Condition | Typical use |
|---|---|---|
| enumerating | the initializer is a `{...}` list | iterating over a parameter pack `{xs...}` or a group of heterogeneous expressions |
| iterating | otherwise, the initializer is an expansion-iterable expression | iterating over a range known at compile time, such as a `constexpr std::array` or a member list obtained by reflection |
| destructuring | otherwise | iterating over `std::tuple`, `std::pair`, aggregates, arrays |

¶3 defines an [[g:expansion-iterable|expansion-iterable]] expression E: E does not have array type, and either the rules of [[stmt.ranged]] find the members `E.begin()` and `E.end()`, or ADL for `begin(E)` and `end(E)` each finds at least one viable candidate function.

Two details are worth noting. Arrays are excluded, because an array can be destructured element by element without running iterators at compile time. And the ADL branch requires a viable candidate, which is stricter than range-based for's mere finding of a declaration; if the `begin` found by ADL cannot be called with E, E is not expansion-iterable, and the expansion statement tries destructuring instead.

A type that both has `begin`/`end` and can be destructured, such as `std::array`, is treated as iterating, so its iteration must be evaluable at compile time.

## The rewrite for each kind

¶5 An expansion statement is equivalent to a compound statement containing the declaration and initialization of the loop variable, plus several instantiations of the loop body.

### Enumerating

```text
{
    init-statement
    S0  ...  SN−1
}
where Si is
    {
        for-range-declaration = Ei ;
        compound-statement
    }
```

¶5.1 N is the number of expressions in the list, and Ei is the i-th one. Each copy Si initializes the loop variable with its own Ei, so `auto` deduces a different type in each copy:

```cpp run ok
#include <cstdio>
template<class... Ts>
void print_all(const Ts&... xs) {
    template for (const auto& x : {xs...}) {
        std::printf("%d\n", static_cast<int>(x));
    }
}
int main() { print_all(1, 2L, 'c'); }   // 1, 2, 99
```

¶6 Example 1 in the standard iterates over several arrays of different lengths, and therefore of different types:

```cpp ok
consteval int f(auto const&... Containers) {
    int result = 0;
    template for (auto const& c : {Containers...}) {
        result += c[0];
    }
    return result;
}
constexpr int c1[] = {1, 2, 3};
constexpr int c2[] = {4, 3, 2, 1};
static_assert(f(c1, c2) == 5);
```

When the list is empty, N is 0 and the loop body is not instantiated at all. A temporary created in some Ei lives until the end of the loop variable initialized with Ei, that is, until the end of that copy Si ([[class.temporary#8]]).

### Iterating

```text
{
    init-statement
    constexpr(opt) decltype(auto) range = ( expansion-initializer ) ;
    constexpr(opt) auto begin = begin-expr ;
    S0  ...  SN−1
}
where Si is
    {
        constexpr(opt) auto iter = begin + decltype(begin - begin){i} ;
        for-range-declaration = * iter ;
        compound-statement
    }
```

¶5.2 N is obtained at compile time by a consteval lambda counting from `begin` to `end`. So *begin-expr* and *end-expr* must be usable in constant evaluation, and the range itself must in effect be a constant. Some points to note:

- `decltype(auto) range = (init)` has parentheses, so an lvalue initializer gives a reference and is not copied.
- The i-th copy gets its iterator directly as `begin + i`, so the iterator must support addition of its difference type.
- The declarations of *range*, *begin* and *iter* carry `constexpr` only if the loop variable declaration does. Then the whole chain of iteration must be constant expressions.
- *i* is a prvalue of type `std::ptrdiff_t`; if it cannot be represented, the program is ill-formed.

¶7 Example 2 in the standard (with the `#include` added here):

```cpp
#include <array>
consteval int f() {
    constexpr std::array<int, 3> arr {1, 2, 3};
    int result = 0;
    template for (constexpr int s : arr) {   // s is a constant and can be an array bound
        result += sizeof(char[s]);
    }
    return result;
}
static_assert(f() == 6);
```

Clang 23 does not yet support iterating expansion statements (it reports iterating expansion statements are not yet supported), so this example could not be verified locally.

Because N must be computed at compile time, run-time containers cannot be used with `template for`. In `std::vector<int> v; template for (auto x : v) { }`, `v` has members `begin`/`end` and is treated as iterating, but iteration over `v` cannot be done in constant evaluation, so the program is ill-formed. Use range-based for for a run-time loop.

### Destructuring

```text
{
    init-statement
    constexpr(opt) auto&& [u0, ..., uN−1] = expansion-initializer ;
    S0  ...  SN−1
}
where Si is
    {
        for-range-declaration = vi ;
        compound-statement
    }
```

¶5.3 N is the [[g:structured-binding-size|structured binding size]] of the initializer's type ([[dcl.struct.bind]]). Any type for which `auto&& [a, b, c] = x;` can be written can be expanded by destructuring: arrays, tuple-like types such as `std::tuple`, and classes whose non-static data members are all public and belong to the same class.

If the initializer is an lvalue, vi is simply ui; otherwise vi is `static_cast<decltype(ui)&&>(ui)`, so the loop variable can be move-constructed from the element. When N is 0 (for an empty struct, say), the rewrite reduces to just `auto&& range = expansion-initializer;`, and the initializer is still evaluated.

¶8 Example 3 in the standard:

```cpp ok
struct S {
    int i;
    short s;
};
consteval long f(S s) {
    long result = 0;
    template for (auto x : s) {   // x is int, then short
        result += sizeof(x);
    }
    return result;
}
static_assert(f(S{}) == sizeof(int) + sizeof(short));
```

Temporaries created in the initializer of an iterating or destructuring expansion statement live until the end of the lifetime of the *range* reference or the structured binding reference ([[class.temporary#9]]).

!!! lawyer "constexpr loop variables and temporaries"
    `template for (constexpr auto e : std::tuple{1, 'c'})` is ill-formed. By ¶5.3 it is rewritten into `constexpr auto&& [u0, u1] = std::tuple{1, 'c'};` at block scope, a constexpr reference bound to a temporary with automatic storage duration, which is not a constant expression. Declaring the tuple as a `static constexpr` variable and expanding that works.

## The loop body is a template definition

[[temp.decls.general#3]] specifies that, for the purposes of name lookup and instantiation, the body of an expansion statement is considered a template definition; [[temp.pre#8]] specifies that entities defined or created in the loop variable declaration or the loop body are templated entities. So expressions in the body that depend on the loop variable are dependent, and their checking is deferred to each copy's instantiation, as in a template.

This means `if constexpr` can discard branches by element type in the loop body even when the enclosing function is not a template:

```cpp run ok
#include <string>
#include <tuple>
#include <type_traits>
std::size_t total() {          // not a template
    std::tuple<int, std::string, double> t{3, "abcd", 1.5};
    std::size_t n = 0;
    template for (auto& e : t) {
        using E = std::remove_cvref_t<decltype(e)>;
        if constexpr (std::is_same_v<E, std::string>)
            n += e.size();     // not instantiated in the int and double copies
        else
            n += static_cast<std::size_t>(e);
    }
    return n;
}
int main() { return total() == 3 + 4 + 1 ? 0 : 1; }
```

Under [[temp.res.general#6]], if no valid instantiation of the loop body could be generated and it is never instantiated (for example, N is 0), the program is ill-formed, no diagnostic required; failed `static_assert`s do not count.

## break and continue

[[stmt.break]] and [[stmt.cont]] both list expansion statements among the statements that can enclose them. `break` ends the whole expansion statement, and none of the remaining Si is executed; `continue` jumps to the end of the compound statement of the current Si, that is, on to the next copy.

```cpp ok
consteval int count() {
    int n = 0;
    template for (auto x : {1, 2, 3, 4}) {
        if (x == 2) continue;   // skip this copy
        if (x == 4) break;      // end the whole expansion statement
        ++n;
    }
    return n;
}
static_assert(count() == 2);    // x is 1 and 3
```

`break` and `continue` change only the run-time flow of control; all N copies of the loop body have already been instantiated. To keep a copy from being instantiated, use `if constexpr`.

[[dcl.attr.fallthrough#1]] also requires the innermost `switch` around a `[[fallthrough]];` to be within its innermost expansion statement; that is, a fallthrough inside an expansion statement cannot pass control to the next `case` of a `switch` outside it.

## Compared with range-based for

| | Range-based for | `template for` |
|---|---|---|
| Category | iteration statement | expansion statement |
| Execution | run-time loop | N copies of the body at compile time |
| Element types | all the same | can differ per copy |
| `{a, b, c}` | `std::initializer_list` | several independent expressions |
| tuples, aggregates | not supported | destructuring |
| Containers | any run-time range | only ranges iterable at compile time |
| Loop body | any statement | compound statement; no jumping in; no labels |
| Amount of code | one copy | N copies |

The main use of expansion statements is with C++26 static reflection: put the member list obtained from a reflection query into a compile-time array, then use an iterating expansion statement to generate code for each member, for automatic serialization, say. Clang 23 supports neither iterating expansion nor reflection, so no example is given here; see [[expr.reflect]].

## Questions

!!! question "1. What kind of expansion statement is this? How many times is the loop body instantiated?"
    ```cpp
    int a[3] = {1, 2, 3};
    template for (int x : a) { }
    ```

<details markdown="1">
<summary>Answer</summary>

Destructuring, 3 times. ¶3 says arrays are not expansion-iterable, and the initializer is not a `{...}` list, so by ¶4.3 it is destructuring, rewritten as `auto&& [u0, u1, u2] = a;`. Since no iteration is involved, `a` need not be a constant.
</details>

!!! question "2. In the loop body of `template for`, are `return;`, a `goto` jumping outside, and `break` each valid?"

<details markdown="1">
<summary>Answer</summary>

All are valid. Being control-flow-limited only forbids jumping in from outside; jumping out is fine, and `break` is explicitly allowed by [[stmt.break]]. The only restriction is that the loop body cannot contain labels ([[stmt.label#4]]), so a `goto` can only target a label outside the expansion statement.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Nature | N independent instantiations of the loop body, not a loop |
| Classification order | `{...}` → enumerating; expansion-iterable → iterating; otherwise → destructuring |
| Enumerating | each copy does `decl = Ei;` |
| Iterating | `decltype(auto) range = (init)`; N counted at compile time; copy i uses `begin + i` |
| Destructuring | `auto&& [u0, ...] = init;`, forwarding for an rvalue initializer |
| `constexpr` | added to the variables in the rewrite only if the loop variable is `constexpr` |
| Control flow | no jumping in; no labels; `break` ends everything, `continue` goes to the next copy |
| Templatedness | the loop body is treated as a template definition, and entities in it are templated entities |
