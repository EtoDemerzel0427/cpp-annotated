---
title: Variadic templates
summary: "Packs and pack expansions: the four kinds of pack, where a pack expansion may appear, which expansion expands a given pack, and what sizeof..., pack indexing, fold expressions and other expansions instantiate to."
updated: 2026-10-19
---

!!! tldr
    - A pack is a name that stands for zero or more elements. There are four kinds: template parameter packs, function parameter packs, init-capture packs (C++20) and structured binding packs (C++26).
    - A pack expansion is a pattern followed by `...`; on instantiation the pattern is instantiated once per element. It can only appear in the 18 contexts the standard lists; a statement like `ts...;` is not valid.
    - A pack name is expanded only by the innermost expansion enclosing it; several packs in one expansion are expanded in lockstep and must have the same number of elements; a pack name that isn't expanded is an error.
    - With an empty pack, a unary fold has a value only for `&&` (`true`), `||` (`false`) and `,` (`void()`); `(ts + ...)` with an empty pack is ill-formed.
    - An empty pack expansion doesn't change the syntactic interpretation: a statement parsed as a variable declaration at the template definition doesn't become a function declaration when the arguments turn out to be empty.

## Packs and pack expansions

```cpp run ok
#include <cstdio>
template<class... Ts>
int print(const Ts&... ts) {
    ((std::printf("%d ", ts)), ...);
    std::puts("");
    return sizeof...(ts);
}
int main() {
    print();            // empty line
    print(1, 2, 3);     // 1 2 3
}
```

A **variadic template** can take any number of template arguments or function arguments. Before C++11, components like `std::bind` and `make_shared` could only use the preprocessor to generate separate overloads for 0, 1, 2, …, N parameters; with variadic templates, one declaration covers every count.

In the example, `Ts` and `ts` are both **packs**: names standing for zero or more elements. `((std::printf("%d ", ts)), ...)` is a **pack expansion**, consisting of a **pattern** `std::printf("%d ", ts)` and an ellipsis; on instantiation the pattern is instantiated once for each element of the pack. `sizeof...(ts)` gives the number of elements.

The related grammar rules are spread over other subclauses: template parameter packs in [[temp.param]], function parameter packs in [[dcl.fct]], captures in [[expr.prim.lambda.capture]], structured binding packs in [[dcl.struct.bind]], folds in [[expr.prim.fold]], pack indexing in [[expr.prim.id]]. This subclause specifies what they have in common.

## The four kinds of pack (¶1–5)

### Template parameter packs (¶1)

¶1 A **template parameter pack** is a template parameter that accepts zero or more template arguments.

```cpp error
template<class... Types> struct Tuple { };

Tuple<> t0;                     // Types is empty
Tuple<int> t1;                  // Types = {int}
Tuple<int, float> t2;           // Types = {int, float}
Tuple<0> bad;                   // error: 0 is not a type
```

All three kinds of template parameter can be packs: type parameter packs `class... Ts`, constant parameter packs `int... Ns` or `auto... Vs`, and template template parameter packs `template<class> class... TTs`. Since C++26 there are also packs of variable templates and concepts as template template parameters ([[temp.param]]).

### Function parameter packs (¶2)

¶2 A **function parameter pack** is a function parameter that accepts zero or more function arguments:

```cpp run ok
template<class... Types> int f(Types... args) { return sizeof...(args); }

int main() {
    return f()            // args is empty
         + f(1)           // args: int
         + f(2, 1.0)      // args: int, double
         - 3;
}
```

The declaration `Types... args` is itself a pack expansion (¶6.1 below): the pattern is `Types args`, it expands the template parameter pack `Types`, and at the same time declares the pack `args`.

### Init-capture packs (¶3)

¶3 An **init-capture pack** is a lambda capture that introduces an init-capture for each element of the pack expansion of its initializer. It was added in C++20 by [[P0780R2]]:

```cpp run ok
#include <memory>
#include <utility>
template<class... Args>
auto make_task(Args... args) {
    return [...xs = std::move(args)]() mutable {   // one move-initialized capture per element
        return (0 + ... + *xs);
    };
}
int main() {
    auto t = make_task(std::make_unique<int>(1), std::make_unique<int>(2));
    return t() - 3;
}
```

In an init-capture, the `...` goes before the name (`...xs = expr`), consistent with declaring a parameter pack `Ts... ts`: the `...` sits immediately to the left of the name being declared, marking that name as a pack.

### Structured binding packs (¶4) {{c++26}}

¶4 A **structured binding pack** is a structured binding name with `...` that introduces zero or more structured bindings ([[dcl.struct.bind]], [[P1061R10]]):

```cpp run ok
struct Point3 { int x, y, z; };

template<class T>
int sum_fields(const T& t) {
    auto& [...fs] = t;                 // fs: x, y, z
    return (fs + ... + 0);
}
template<class T>
int tail_count(const T& t) {
    auto& [first, ...rest] = t;        // rest: y, z
    (void)first;
    return sizeof...(rest);
}
int main() {
    Point3 p{1, 2, 3};
    return sum_fields(p) - 6 + tail_count(p) - 2;
}
```

A structured binding declaration has at most one pack; its number of elements is the total minus the number of other names, and can be zero. A declaration containing a structured binding pack must declare a templated entity ([[dcl.pre#7]]), so it can only appear in a templated context such as a template or a generic lambda:

```cpp error
struct P { int a, b; };
int f() {
    auto [...xs] = P{1, 2};    // error: not in a templated context
    return sizeof...(xs);
}
```

A pack expansion is only replaced by the list of elements at template instantiation, and non-template code has no instantiation step. If you need one in an ordinary function, wrap the code in a generic lambda.

### Number of elements (¶5)

¶5 A pack is any of the four kinds above. The number of elements of a template parameter pack or function parameter pack is the number of arguments provided for it; for an init-capture pack, the number of elements in the pack expansion of its initializer; for a structured binding pack, as specified in [[dcl.struct.bind]].

## Where a pack expansion can appear (¶6)

¶6 A pack expansion consists of a pattern and an ellipsis, and its instantiation produces a list of zero or more instantiations of the pattern. The form of the pattern depends on the context of the expansion, and these are the only contexts allowed:

| ¶ | Context | Pattern | Example |
|---|---|---|---|
| 6.1 | function parameter pack [[dcl.fct]] | the parameter declaration without the ellipsis | `void f(Ts... ts)` |
| 6.2 | using-declaration [[namespace.udecl]] | *using-declarator* | `using Bs::operator()...;` |
| 6.3 | friend type declaration [[class.mem.general]] {{c++26}} | *friend-type-specifier* | `friend Ts...;` |
| 6.4 | template parameter pack that is itself a pack expansion [[temp.param]] | the parameter declaration without the ellipsis | `template<Ts... vs>` |
| 6.5 | *initializer-list* [[dcl.init]] | *initializer-clause* | `g(args...)`, `int a[]{ts...}` |
| 6.6 | base specifier list [[class.derived]] | *base-specifier* | `struct D : Bs...` |
| 6.7 | mem-initializer naming a base class | *mem-initializer* | `D() : Bs(0)...` |
| 6.8 | template argument list [[temp.arg]] | template argument | `tuple<Ts*...>` |
| 6.9 | attribute list [[dcl.attr.grammar]] | attribute | `[[vendor::attr...]]` |
| 6.10 | annotation list {{c++26}} | annotation | `[[=Vs...]]` |
| 6.11 | alignment specifier [[dcl.align]] | the `alignas` without the ellipsis | `alignas(Ts...)` |
| 6.12 | capture list [[expr.prim.lambda.capture]] | the capture without the ellipsis | `[args...]`, `[&args...]`, `[...xs = args]` |
| 6.13 | `sizeof...` | identifier | `sizeof...(Ts)` |
| 6.14 | pack index expression {{c++26}} | identifier | `ts...[0]` |
| 6.15 | pack index type {{c++26}} | *typedef-name* | `Ts...[0]` |
| 6.16 | pack index template name {{c++29}} | *simple-template-name* | `TTs...[0]<int>` |
| 6.17 | fold expression [[expr.prim.fold]] | the operand containing an unexpanded pack | `(ts + ...)` |
| 6.18 | fold expanded constraint [[temp.constr.fold]] {{c++26}} | the constraint | `requires (C<Ts> && ...)` |

Example 5 in the standard is `f(&rest...)`: `&rest...` is a pack expansion and `&rest` is its pattern.

Expansion isn't allowed anywhere outside the table. `ts...;`, `g(ts)...;` and `x = ts...;` are all invalid. Before C++17, executing a statement for each element required smuggling the expansion into an *initializer-list* (6.5) through array initialization: `int dummy[] = {(g(ts), 0)...};`. Since C++17 this is written as a comma fold `(g(ts), ...);` (6.17).

A few more points:

- A mem-initializer can only expand base classes (6.7). Data members all have their own names and there are no member packs, so `: a(as)...` is ill-formed.
- An attribute list can be expanded syntactically, but each attribute must itself allow `...`, and no standard attribute does, so this only matters for vendor attributes.
- 6.4 lets parameter types come from an outer pack: in `template<class... Ts> struct X { template<Ts... vs> struct Y; };`, `X<int, char>::Y` takes one `int` constant and one `char` constant.

```cpp run ok
#include <cstdio>
// 6.2 + 6.6: the overload idiom
template<class... Fs> struct overload : Fs... { using Fs::operator()...; };

// 6.6 + 6.7: one mem-initializer per base
struct B1 { int a; };
struct B2 { int b; };
template<class... Bases> struct D : Bases... {
    D(Bases... bs) : Bases(bs)... { }
};

// 6.11: take the strictest alignment
template<class... Ts> struct alignas(Ts...) Storage { unsigned char buf[16]; };
static_assert(alignof(Storage<char, double, short>) == alignof(double));

// 6.4: parameter types come from the outer pack
template<class... Ts> struct X { template<Ts... vs> struct Y { }; };
X<int, char>::Y<1, 'c'> y;

// 6.12: capture a pack by reference
template<class... Args> auto summer(Args&... args) { return [&args...] { return (args + ...); }; }

int main() {
    auto o = overload{[](int) { return 1; }, [](double) { return 2; }};
    D<B1, B2> d{B1{1}, B2{2}};
    int a = 1, b = 2;
    std::printf("%d %d %d\n", o(1), o(1.0), summer(a, b)());   // 1 2 3
    (void)d; (void)y;
}
```

¶7 Many rules are written for non-pack entities, such as the requirements on function parameters in [[dcl.fct]], or that a constant template parameter must be of structural type. When deciding whether a pack satisfies such a rule, it is treated as the entities that would result from instantiating the pattern. Thanks to this, the standard doesn't need to add "or a pack of …" everywhere.

## Which expansion expands which pack (¶8)

¶8 specifies which expansion expands a pack:

1. A pack name appearing in the pattern of a pack expansion is expanded by that expansion.
2. Each appearance of a pack name is expanded only by the innermost enclosing expansion.
3. The pattern must contain at least one pack that isn't expanded by a nested expansion; these are the pattern's **unexpanded packs**.
4. All packs expanded by one expansion must have the same number of elements; they are expanded in lockstep.
5. A pack name that appears but isn't expanded by any expansion makes the program ill-formed.

```cpp error
template<typename...> struct Tuple { };
template<typename T1, typename T2> struct Pair { };

template<class... Args1> struct zip {
    template<class... Args2> struct with {
        typedef Tuple<Pair<Args1, Args2>...> type;   // Args1 and Args2 expanded in lockstep
    };
};

typedef zip<short, int>::with<unsigned short, unsigned>::type T1;
    // OK: Tuple<Pair<short, unsigned short>, Pair<int, unsigned>>
typedef zip<short>::with<unsigned short, unsigned>::type T2;
    // error: Args1 and Args2 have different numbers of elements

template<class... Args> void f(Args...);
template<class... T> int h(T...);

template<class... Args>
void g(Args... args) {                      // OK: Args is expanded by the function parameter pack args
    f(const_cast<const Args*>(&args)...);   // OK: Args and args expanded in lockstep
    f(5 ...);                               // error: pattern contains no pack
    f(args);                                // error: args is not expanded
    f(h(args...) + args...);                // OK
}
```

The last line has two `args`. The innermost expansion of the first is the argument `args...` of `h`, where it is fully expanded; the pattern of the outer expansion is `h(args...) + args`, whose only unexpanded pack is the second `args`. So when `args` is `{a, b}`, the result is `f(h(a, b) + a, h(a, b) + b)`.

Expanding the same pack once at an inner level and once at an outer level gives pairwise combinations:

```cpp run ok
#include <tuple>
#include <type_traits>
template<class... Ts>
auto square(Ts... ts) {
    return std::tuple{ std::tuple{ts, ts...}... };   // in the outer pattern only the first ts is unexpanded
}
int main() {
    auto p = square(1, 2);
    // p == tuple{ tuple{1, 1, 2}, tuple{2, 1, 2} }
    static_assert(std::is_same_v<decltype(p),
        std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>>);
    return std::get<2>(std::get<0>(p)) - 2;
}
```

Lockstep expansion is often used to pair a pack with a list of indices:

```cpp run ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>
template<class T, std::size_t... Is>
auto reverse_impl(const T& t, std::index_sequence<Is...>) {
    return std::tuple{ std::get<sizeof...(Is) - 1 - Is>(t)... };
}
template<class... Ts>
auto reverse(const std::tuple<Ts...>& t) {
    return reverse_impl(t, std::index_sequence_for<Ts...>{});
}
int main() {
    auto r = reverse(std::tuple{1, 2.0, 'c'});
    static_assert(std::is_same_v<decltype(r), std::tuple<char, double, int>>);
    return std::get<2>(r) - 1;
}
```

`sizeof...(Is)` is itself a pack expansion (6.13) that fully expands `Is`. So in the outer pattern `std::get<sizeof...(Is) - 1 - Is>(t)`, only the last `Is` is unexpanded.

## Instantiation (¶9–17)

### Substituting element by element (¶9)

¶9 When a pack expansion is instantiated and the expanded packs have N elements, E₁, E₂, …, E_N are produced in order: the ith is obtained by replacing each expanded pack in the pattern with its ith element. The substituted elements are understood as follows:

- ¶9.1 template parameter pack: an element of a type parameter pack is a *typedef-name*, of a constant parameter pack an *id-expression*, of a template template parameter pack a *template-name*, each referring to the ith argument;
- ¶9.2 function parameter pack: an *id-expression* designating the ith function parameter;
- ¶9.3 init-capture pack: an *id-expression* designating the variable introduced by the ith capture;
- ¶9.4 structured binding pack: an *id-expression* designating the ith structured binding.

An element being a *typedef-name* means the substitution is not textual. With `Ts` being `{int&}`, `const Ts&` gives `int&`: const applied to a reference type is ignored, and the two references collapse into one. Textual substitution would give the invalid `const int& &`.

### An empty pack doesn't change the syntax (¶9)

!!! std
    When N is zero, the instantiation of a pack expansion does not alter the syntactic interpretation of the enclosing construct, even in cases where omitting the pack expansion entirely would otherwise be ill-formed or would result in an ambiguity in the grammar.

When N is zero, the pack expansion doesn't change the syntactic interpretation of the enclosing construct, even if deleting the expansion entirely would make it ill-formed or ambiguous. Parsing was done at the template definition, and instantiation doesn't reparse. The example in ¶17 shows this:

```cpp run ok
template<class... T> struct X : T... { int v; };
template<class... T> int f(T... values) {
    X<T...> x(values...);      // parsed at definition as direct-initialization of variable x
    return x.v;
}
template int f<>();            // OK: X<> has no base classes
int main() { return f<>(); }   // returns 0
```

Delete `values...` and the resulting `X<> x();` would be a function declaration in ordinary code (the most vexing parse). But here `x` was already determined to be a variable at the template definition, and instantiation doesn't change that. An empty `()` initializer means value-initialization; `X<>` has no user-provided constructor, so it is zero-initialized first and `x.v` is 0.

### sizeof... (¶10)

¶10 A `sizeof...` expression instantiates to an integral constant with value N, of type `std::size_t` ([[expr.sizeof]]). Its operand can only be a pack name:

```cpp error
template<class... Ts> int h(Ts... ts) { return sizeof...(ts) + sizeof...(Ts); }   // OK
int x = 3;
int k = sizeof...(x);           // error: x is not a pack
```

### Pack indexing (¶11–13) {{c++26}}

¶11–13 C++26 pack indexing ([[P2662R3]]) takes the Kth element of a pack directly: a pack index expression `ts...[K]` instantiates to the *id-expression* E_K, a pack index type `Ts...[K]` to the *typedef-name* E_K, and a pack index template name to the *simple-template-name* E_K. K must be a converted constant expression of type `std::size_t`, with 0 ≤ K < N ([[expr.prim.id]], [[dcl.type]], [[temp.names]]).

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
template<auto... Vs>  constexpr auto second = Vs...[1];

template<class... Ts>
auto last_arg(Ts... ts) { return ts...[sizeof...(ts) - 1]; }

static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);
static_assert(second<1, 2, 3> == 2);
int main() { return last_arg(1, 2.0, 3) - 3; }
```

```cpp error
template<class... Ts> using At5 = Ts...[5];
At5<int, char> a;               // error: index out of range
```

Pack indexing is itself a pack expansion, so no further `...` is needed. The compiler picks the element by index directly, without instantiating helper templates the way `std::tuple_element_t<I, std::tuple<Ts...>>` does.

!!! warning "Clang support"
    Clang 23 supports pack index types and pack index expressions, but not yet pack index template names: `TTs...[0]<int>` gives a syntax error.

### Alignment specifiers (¶14)

¶14 `alignas(Ts...)` instantiates to `alignas(E₁) alignas(E₂) … alignas(E_N)`, and with several `alignas` the strictest applies ([[dcl.align]]). When N is zero it produces nothing, which is the same as having no alignment requirement.

### Fold expressions (¶15)

¶15 Fold expressions instantiate to the following shapes, where *op* is the fold-operator and E in a binary fold is the operand that contains no unexpanded pack:

| Form | Name | Expands to |
|---|---|---|
| `(... op pack)` | unary left fold | `(((E₁ op E₂) op …) op E_N)` |
| `(pack op ...)` | unary right fold | `(E₁ op (… op (E_{N−1} op E_N)))` |
| `(init op ... op pack)` | binary left fold | `(((init op E₁) op E₂) op … op E_N)` |
| `(pack op ... op init)` | binary right fold | `(E₁ op (… op (E_N op init)))` |

With `...` on the left it associates to the left; on the right, to the right.

```cpp run ok
template<class... Args>
bool all(Args... args) { return (... && args); }   // ((E1 && E2) && E3) && E4

template<class... Args>
int minus_left(Args... args)  { return (... - args); }   // (1 - 2) - 3 == -4
template<class... Args>
int minus_right(Args... args) { return (args - ...); }   // 1 - (2 - 3) == 2

int main() {
    bool b = all(true, true, true, false);
    return (b ? 1 : 0) + (minus_left(1, 2, 3) + 4) + (minus_right(1, 2, 3) - 2);
}
```

With an empty pack, a unary fold has a value for only three operators (Table 20 [tab:temp.fold.empty]); for any other operator the instantiation is ill-formed:

| Operator | Value for an empty pack |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

A binary fold always has a value; with an empty pack the result is `init`:

```cpp error
template<class... Ts> auto sum(Ts... ts) { return (ts + ...); }
template<class... Ts> auto sum0(Ts... ts) { return (ts + ... + 0); }
int a = sum0();                 // OK: binary fold, result is 0
int b = sum(1, 2);              // OK
int c = sum();                  // error: unary fold over + can't take an empty pack
```

`+` has no default value of 0 because `+` can be overloaded and its identity element depends on the type: for string concatenation it is the empty string, for matrix addition the zero matrix. The original proposal [[N4295]] also specified empty-pack values for `+`, `*`, `&` and `|`; before C++17 shipped, [[P0036R0]] removed them, keeping only the three that are type-independent (see also [[expr.prim.fold]]). When you need an identity element, write a binary fold and give the initial value explicitly.

### Fold expanded constraints (¶16) {{c++26}}

¶16 A fold expanded constraint is not instantiated. The fold in `template<class... Ts> requires (C<Ts> && ...)` becomes a fold expanded constraint during constraint normalization ([[temp.constr.fold]]), and checking it checks `C` for each element in order; for `&&`, it stops at the first unsatisfied element and the later elements are not substituted. It is never first instantiated into one big expression, which is why two such constraints can be compared element by element for subsumption ([[temp.constr.order]]).

### Other expansions (¶17)

¶17 All other pack expansions instantiate to a list E₁, E₂, …, E_N, whose kind depends on the context, such as an expression list, a base specifier list or a template argument list. When N is zero the list is empty: with an empty pack, `struct X : T...` has no base classes, `f(args...)` is a call with no arguments, and `tuple<Ts...>` is `tuple<>`.

## Packs in deduction

The following rules live in other subclauses, but you run into them often when writing variadic templates:

- A function parameter pack can be deduced from call arguments only if it is at the end of the parameter list. In the middle it is a non-deduced context ([[temp.deduct.type]]), and unless specified explicitly it is deduced as an empty pack.
- The template parameter pack of a primary class template, primary variable template or alias template must be the last template parameter. In a function template, template parameters can follow the pack as long as they can be deduced or have defaults ([[temp.param]]).
- In partial ordering, when two templates are otherwise equal, the one without a trailing function parameter pack is more specialized ([[temp.deduct.partial#11]]); see [[temp.func.order]].

```cpp error
template<class... Ts, class Last>
void back(Ts..., Last) { }
int main() {
    back(1, 2, 3);             // error: Ts deduced as empty, the function has only one parameter
    back<int, int>(1, 2, 3);   // OK: Ts = {int, int}, Last deduced from the third argument
}
```

!!! impl "Compile-time cost"
    Most C++11/14 variadic techniques rely on recursive instantiation: peel off the first element and recurse on the rest. N elements produce N specializations, each carrying an argument list of length O(N), for a total cost of O(N²). Fold expressions, pack indexing, and `std::index_sequence` with lockstep expansion can all replace such recursion with a single level of expansion. Compilers cap the depth of recursive instantiation; Clang and GCC let you adjust it with `-ftemplate-depth=`.

!!! history "History"
    | Standard | Change |
    |---|---|
    | C++11 | variadic templates, template and function parameter packs, pack expansions, `sizeof...` ([[N2242]]) |
    | C++17 | fold expressions ([[N4295]]); expansion in using-declarations `using Bs::f...;` ([[P0195R2]]) |
    | C++20 | init-capture packs `[...xs = args]` ([[P0780R2]]) |
    | C++26 | pack indexing ([[P2662R3]]); structured binding packs ([[P1061R10]]); variadic friends `friend Ts...;` ([[P2893R3]]); expansion in annotation lists; fold expanded constraints |

!!! pitfall "Comma folds and overloaded commas"
    The built-in comma operator evaluates left to right, so `(f(args), ...)` calls `f` in argument order. But if the return type of `f` overloads `operator,`, the fold calls that overload. The safe form is `(void(f(args)), ...)`.

## Questions

!!! question "Question 1"
    Given `args` is `{a, b}` and `Args` is `{A, B}`, what does each expansion produce?

    ```cpp
    f(g(args)...);                 // (1)
    f(g(args...));                 // (2)
    f(g(args, args...)...);        // (3)
    f(sizeof...(Args) + args...);  // (4)
    ```

<details markdown="1">
<summary>Answer</summary>

1. `f(g(a), g(b))`; the pattern is `g(args)`.
2. `f(g(a, b))`; the expansion happens in the argument list of `g`.
3. `f(g(a, a, b), g(b, a, b))`. The inner `args...` is fully expanded first, and in the outer pattern `g(args, args...)` only the first `args` is unexpanded.
4. `f(2 + a, 2 + b)`. `sizeof...(Args)` is a complete expansion by itself, and the only unexpanded pack in the outer pattern is `args`.
</details>

!!! question "Question 2"
    Why does calling `template<class... Ts> void f(Ts..., int)` as `f(1, 2)` fail, while `f<int>(1, 2)` succeeds?

<details markdown="1">
<summary>Answer</summary>

A function parameter pack that isn't at the end of the parameter list is a non-deduced context ([[temp.deduct.type]]), so deduction assigns it no arguments. A trailing template parameter pack that is neither deduced nor explicitly specified is deduced as an empty pack ([[temp.arg.explicit]]), so the function type is `void(int)`: two arguments for one parameter, not viable. With `Ts = {int}` specified explicitly, the function type is `void(int, int)`, which is viable.
</details>
