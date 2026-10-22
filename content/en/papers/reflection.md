---
title: Static reflection (P2996)
summary: C++26 lets a program query types, members and enumerators at compile time as std::meta::info values, and splice them back into code with [: :]. Why it chose a single opaque value-based type, why the token is ^^, how access control and error handling were settled, and which capabilities were deferred.
tags: reflection, metaprogramming, consteval, C++26, proposal
group: C++26
updated: 2026-10-19
---

!!! tldr
    - Before C++26, converting an enum to a string or iterating over a struct's members could only be done with macros, code generation, or template tricks that depend on compiler details, because the language does not provide members' names or lists.
    - [[P2996R13]] represents every program construct as a value of a single opaque type, `std::meta::info`: `^^X` obtains a reflection, `consteval` functions query it, and `[: r :]` splices it back into code.
    - A single type was chosen rather than a family of types to avoid hard-coding the language's taxonomy into the library's type system; the token went from `reflexpr` to `^`, and then to `^^` because of a conflict with Clang's blocks extension.
    - Access control is decided by an `access_context` the caller passes explicitly, with `unchecked()` as an auditable way to bypass it; failed queries throw `std::meta::exception`.
    - Range splicing, expression reflection and general code injection were all deferred; in C++26, `define_aggregate` can only complete the definition of a class.

## Before reflection

One of the most common needs is turning an enum value into its name. The language does not provide enumerator names, and the common approach is the X-macro: write the list of enumerators as a macro and expand it twice, once to generate the enum definition and once to generate a `switch`.

```cpp run title="xmacro.cpp" ok
#include <cstdio>
#include <string_view>

#define COLORS(X) X(red) X(green) X(blue)

enum class Color {
#define AS_ENUM(name) name,
  COLORS(AS_ENUM)
#undef AS_ENUM
};

constexpr std::string_view to_string(Color c) {
  switch (c) {
#define AS_CASE(name) case Color::name: return #name;
    COLORS(AS_CASE)
#undef AS_CASE
  }
  return "<unnamed>";
}

static_assert(to_string(Color::green) == "green");

int main() {
  std::printf("%s\n", to_string(Color::blue).data());
}
```

It works, at the cost that the enum must be defined in the macro's format. Existing enums in third-party libraries can't use this approach.

Another family of approaches relies on compiler extensions. The contents of `__PRETTY_FUNCTION__` include the template arguments, and libraries like magic_enum cut enumerator names out of that string:

```cpp run title="pretty.cpp" impl
#include <cstdio>
#include <string_view>

enum class Color { red, green, blue };

template <auto V>
constexpr std::string_view name_of() {
  return __PRETTY_FUNCTION__;  // compiler extension; format is up to the implementation
}

int main() {
  std::printf("%s\n", name_of<Color::green>().data());
  std::printf("%s\n", name_of<static_cast<Color>(7)>().data());
}
```

Clang 23 prints `std::string_view name_of() [V = Color::green]` and `std::string_view name_of() [V = (Color)7]`. A library has to parse such strings per compiler, and then instantiate the template for each value in an integer range to see which values print a name.

Structs have the same problem. Boost.PFR's approach is to try aggregate initialization with a placeholder object convertible to any type, infer the number of fields from how many initializers are accepted, and then extract the fields with structured bindings:

```cpp run title="pfr.cpp" ok
#include <cstddef>
#include <cstdio>
#include <string>
#include <tuple>
#include <utility>

struct any_init {
  template <class T> operator T() const;  // declared only, not defined
};

// if T can be aggregate-initialized with N any_inits, T has at least N fields
template <class T, std::size_t... I>
consteval bool init_with(std::index_sequence<I...>) {
  return requires { T{(void(I), any_init{})...}; };
}

template <class T, std::size_t N = 0>
consteval std::size_t field_count() {
  if constexpr (!init_with<T>(std::make_index_sequence<N + 1>{}))
    return N;
  else
    return field_count<T, N + 1>();
}

template <class T>
auto to_tuple(T& t) {
  constexpr auto n = field_count<T>();
  if constexpr (n == 1) { auto& [a] = t; return std::tie(a); }
  else if constexpr (n == 2) { auto& [a, b] = t; return std::tie(a, b); }
  else if constexpr (n == 3) { auto& [a, b, c] = t; return std::tie(a, b, c); }
  else static_assert(n <= 3, "add another line to support more fields");
}

struct Point { int x; double y; std::string label; };
static_assert(field_count<Point>() == 3);

int main() {
  Point p{1, 2.5, "origin"};
  auto [x, y, label] = to_tuple(p);
  std::printf("%d %g %s\n", x, y, label.c_str());
}
```

This trick only works for aggregates, and it can be fooled by brace elision: in our test, `struct Pair { int a[2]; int b; }` has only two members, yet `field_count<Pair>()` gives 3, because the two elements of the array member each consume an `any_init`. It also cannot get the names of the fields, which is exactly what serialization needs.

C++26's expansion statement `template for` ([[P1306R5]], [[stmt.expand]]) can iterate over an object that supports structured bindings, and Clang 23 already supports it:

```cpp run title="values.cpp" ok
#include <iostream>
#include <string>

struct Point { int x; double y; std::string label; };

template <class T>
void print_values(const T& obj) {
  template for (const auto& v : obj) {  // destructuring expansion statement
    std::cout << v << ' ';
  }
  std::cout << '\n';
}

int main() {
  print_values(Point{1, 2.5, "origin"});  // 1 2.5 origin
}
```

Still, all you get is the values. What a member is called, whether it is `private`, what attributes it carries: the compiler has all this information, but the language gives the program no channel to read it. That is what reflection fills in.

## The design space

### Is a reflection a type or a value

C++'s first reflection design was the Reflection TS: `reflexpr(X)` produced a meta-object type, and queries were traits-style templates. The later [[P1240R2]] switched to a value-based approach: every reflection is a value of the same type, `std::meta::info`, and queries are ordinary `consteval` functions (that is, **immediate functions**, every call to which must be evaluated at compile time, [[g:immediate-function]]). The background of this shift, a comparison of the two styles and the compile-time cost argument are in section six of [[history/template-metaprogramming]] and not repeated here.

The direct benefit of the value-based approach is that metaprogramming becomes ordinary programming. `members_of` returns a `std::vector<std::meta::info>`, which can be processed with `for` loops, `if`, subscripts and standard algorithms, with no more recursive templates. This relies on C++20 allowing `new` during constant evaluation ([[history/constexpr]]).

### One type or a family of types

P2996 says the most common suggested change to P1240 was to split the single `info` into a family of types, such as `std::meta::type` and `std::meta::variable`, so function signatures could express which kind of reflection they accept. The authors consider this a serious mistake (P2996R13 §2.2).

The reason is that it would hard-code the language's taxonomy into the library's type system. The paper's example: had C++03 standardized a `std::meta::variable` representing variables, then when C++11 extended the definition of variable to include references, lots of code would already have depended on the old type split, making the extension hard. The semantics of a standard type are nearly impossible to change once published, while the language's taxonomy will keep changing.

The paper lists some additional benefits:

- it makes no assumptions about compilers' internal representations and favors no particular implementation;
- when the language adds new constructs, no new types are needed;
- a `std::vector<std::meta::info>` can hold a mixed template argument list, types and values together, with no slicing problems between base and derived classes.

The cost is that type checking is deferred to the call: passing a reflection of a type to `enumerators_of`, which only accepts enumerations, is not reported until constant evaluation; the form of the error is described in the error handling section below.

### The token: from reflexpr to ^^

P1240 kept the TS keyword `reflexpr(e)`. In discussion people found it too heavy and too much like a function call, so SG7 changed it to unary `^`, the upward arrow suggesting lifting (P2996R13 §4.1.1).

`^` was later found to conflict with Clang's blocks extension. Blocks are a closure syntax Apple added to C and Objective-C, and Clang supports them in C++ too. [[P3381R0]] points out that `type-id(^ident)();` can be read either as declaring a block variable or as converting the reflection of `ident` to `type-id` and then calling it. Clang 23 treats `^` as a block:

```cpp run title="blocks.cpp" impl cc=clang_trunk flags="-std=c++2c -fblocks"
int main() {
  int (^ident)() = ^{ return 42; };  // Clang's blocks extension: ident is a block
  return ident() == 42 ? 0 : 1;
}
```

With `-fblocks` this code compiles and runs; and when Clang 23, which doesn't support reflection, meets `^^int`, the diagnostic it gives is also `block pointer to non-function type is invalid`.

P3381R0 ruled out the other single characters one by one: `#e` already means stringizing in macros; `$e` conflicts with identifiers starting with `$`, which many compilers allow; `%e`, written as `C<%T>`, has `<%` as a digraph for `{`. In the end `^^` was chosen as a new token. The paper also explains why not to go back to a keyword: reflection itself is not what the code is trying to express; it is a price paid because entities are not ordinary values. Writing `f(^^int, ^^float)` is already a compromise, and there is no reason to make it more prominent.

### Splicing: [: :]

The operation that turns a reflection back into code is called **splicing**. The early design used `unreflexpr(...)`; P1240R0 found that a single splice syntax could not be parsed, since types and templates must be distinguished, and SG7 finally chose `[: r :]`, preceded by `typename` or `template` for disambiguation when needed (P2996R13 §4.2.4).

Different left and right delimiters were chosen, first because the spliced expression may contain low-precedence operators, and second to allow nested splices. `[:` and `:]` were made single tokens so that `arr[[:r:]]` is easy to handle; the cost is a special rule, like the one for `<::`, to preserve the original meaning of `arr[::N]` ([[lex.pptoken#5.3]]).

P1240 also had a range splice, `[: ... r :]`, expanding a list of reflections into a pack. P2996 did not include it, on the grounds that range splicing of dependent arguments is at least an order of magnitude harder to implement, and leaving it out improved the chances of making C++26. Today its uses are served by `template for`.

### Access control: who is asking

Whether reflection can see `private` members is one of the oldest arguments about reflection. [[P3547R1]] summarizes the positions: some consider complete introspection of classes a basic requirement of reflection; some worry that users will accidentally obtain reflections of private members and require intent to be expressed explicitly; and a few think the capability should not be provided at all.

The most direct idea is to add an `is_accessible(r)` that checks access from the point of the call. P3547R1 shows that libraries written this way don't compose (adapted from the paper, not compiled):

```cpp
consteval auto accessible_nsdms_of(info cls) -> vector<info> {
  vector<info> result;
  for (auto m : nonstatic_data_members_of(cls))
    if (is_accessible(m))   // checked from where?
      result.push_back(m);
  return result;
}

class Cls {
  int priv;
  friend void client();
};

void client() {
  static_assert(accessible_nsdms_of(^^Cls).size() > 0);  // fails
}
```

`is_accessible` is called inside `accessible_nsdms_of`, which is not a friend of `Cls`, so `client`'s friendship is lost. Checking from where constant evaluation begins doesn't work either: if a `consteval` friend function is called from `main`, evaluation begins in `main`, and friendship is lost just the same.

P3547R1's conclusion is not to guess, but to have the caller pass the context explicitly. In the final design, functions such as `members_of`, `nonstatic_data_members_of` and `bases_of` require a second argument, a `std::meta::access_context` ([[meta.reflection.access.context]]), which can only be obtained from three functions:

| Function | Context it represents |
|---|---|
| `access_context::current()` | The nearest enclosing namespace, class or function of the call site ([[meta.reflection.access.context#5]]) |
| `access_context::unprivileged()` | The global namespace; only public members are visible |
| `access_context::unchecked()` | All members are accessible |

There is no way to forge a more privileged context. A library that needs to see private members must write `unchecked()`, which is easy to spot in code review. Library functions pass `ctx` down as a parameter, and the caller's friendship travels along with it.

The other half of the rule is on the splicing side: once a member is designated via `[: m :]`, it can be accessed from anywhere ([[class.access.base#5]]). Access control is checked once, when the reflection is obtained, not again when it is used.

### What to do when a query fails

A call like `template_of(^^int)` has no reasonable result. [[P3560R2]] lists four options: return an invalid reflection, like NaN; return `std::expected`; make the call not a constant expression; or throw an exception.

An invalid reflection doesn't work for functions returning `vector`; not being a constant expression is consistent, but users have no way to recover. P2996R13 leaned toward exceptions, with an example of how `std::expected` goes wrong: in `requires (template_of(^^T) == ^^std::optional)`, comparing an `expected` with an `info` quietly yields `false`, masking the error. The usual concerns about exceptions, such as run-time overhead and object file size, don't exist at compile time. In the end C++26 adopted exceptions: a failed query throws `std::meta::exception` ([[meta.reflection.exception]]), which can be caught within the same constant evaluation. Compile-time exceptions themselves are covered in [[papers/constexpr-exceptions]].

### Removed and deferred

P2996 says explicitly that it is a subset of P1240, starting small to get into the language sooner (§2). The following were deferred:

- Expression reflection. Early revisions allowed reflecting constant expressions. After P2996 itself introduced side effects in constant evaluation, the same constant expression would have to be re-evaluated on every splice, which made this path unworkable; the paper defers it to a future `^^(expr)` syntax (§4.1).
- Range splicing, for the reasons above.
- General code injection. P2996 considers code injection along the lines of [[P2237R0]] worth pursuing, but C++26 has only `define_aggregate`, which adds data members to an incomplete class. [[P3294R2]], which describes injected code with token sequences, had not been adopted at the time of writing.

## The final design and wording

### An example

Below is a function, written per the current draft, that prints a struct's field names and values. Clang 23 doesn't support `^^` and has no `<meta>` header, so this code has not been compiled and carries no verdict:

```cpp
#include <meta>
#include <print>
#include <string>

struct Point { int x; double y; std::string label; };

template <class T>
void print_fields(const T& obj) {
  constexpr auto ctx = std::meta::access_context::current();
  template for (constexpr std::meta::info m :
                std::define_static_array(
                    std::meta::nonstatic_data_members_of(^^T, ctx))) {
    std::println("{} = {}", std::meta::identifier_of(m), obj.[:m:]);
  }
}

int main() {
  print_fields(Point{1, 2.5, "origin"});
}
```

Each component corresponds to a piece of wording:

| Component | Role | Subclause |
|---|---|---|
| `^^T` | The reflection operator, giving a prvalue of type `std::meta::info` | [[expr.reflect#1]] |
| `std::meta::info` | A new fundamental type; its values are called reflections, and there is a unique null reflection | [[basic.fundamental#17]] |
| `nonstatic_data_members_of(^^T, ctx)` | Filters the members accessible per `ctx`, returned in declaration order | [[meta.reflection.member.queries#4]] |
| `define_static_array` | Copies a compile-time `vector` into an array with static storage | [[meta.define.static]] |
| `template for` | Instantiates the loop body once per element; `m` is a constant each time | [[stmt.expand#5]] |
| `obj.[:m:]` | Splices the member, forming a member access expression | [[basic.splice#1]], [[expr.prim.splice]] |
| `identifier_of(m)` | Gets the member's name | [[meta.reflection.names]] |

`define_static_array` cannot be omitted. When the loop variable is declared `constexpr`, the expansion statement stores the range in a `constexpr` variable ([[stmt.expand#5.2]]), and memory a `std::vector` allocates during constant evaluation cannot outlive the evaluation. The `define_static_string` and `define_static_array` provided by [[P3491R3]] exist precisely to promote results to static storage while compile-time allocations still cannot persist.

### New subclauses

Reflection is spread over both the language and library parts of the draft:

- [[expr.reflect]]: the syntax of the reflection operator and what each kind of operand gives. `^^` takes the longest possible token sequence, so the `&&` in `^^int && true` is taken as an rvalue reference declarator ([[expr.reflect#3]]).
- [[basic.splice]], [[expr.prim.splice]], [[dcl.type.splice]]: splice specifiers, and what they mean in expression and type positions.
- [[expr.const.const]]: which values must stay at compile time, discussed in detail in the next section.
- [[expr.const.reflect]]: where the **injected declarations** produced by `define_aggregate` are placed, and how results are kept independent of evaluation order.
- [[meta.reflection]]: all the query functions in the `<meta>` header, `access_context` and `std::meta::exception`.

### Companion proposals

Several proposals went into C++26 along with P2996, each filling in a piece:

| Proposal | Contents | Subclause |
|---|---|---|
| [[P1306R5]] | Expansion statements, `template for` | [[stmt.expand]] |
| [[P3289R1]] | `consteval { ... }` blocks | [[dcl.pre#15]] |
| [[P3394R4]] | Annotations, `[[=expr]]` | [[dcl.attr.annotation]] |
| [[P3491R3]] | `define_static_string`, `define_static_array` and others | [[meta.define.static]] |

The motivation for consteval blocks comes from `define_aggregate`. The whole point of that call is its side effect, and previously it could only be stuffed into `static_assert(is_type(define_aggregate(...)))`, which reads as if it were asserting something. P3289R1 provides a dedicated place, and the draft specifies that expressions that can produce injected declarations may only appear in consteval blocks ([[expr.const.core#2.32]]):

```cpp
struct Storage;
consteval {
  std::meta::define_aggregate(^^Storage, {
    std::meta::data_member_spec(^^int, {.name = "x"}),
  });
}
Storage s{42};   // Storage now has an int member x
```

Annotations solve the problem of attaching information to declarations. Attributes won't do, because they may be ignored by implementations and have no value to return. P3394R4 adds an `=` to the attribute syntax, followed by a constant expression whose value can be read with `annotations_of`:

```cpp
struct Skip {};
struct Config {
  int port;
  [[=Skip{}]] std::string cache;   // skipped when serializing
};
// annotations_of_with_type(^^Config::cache, ^^Skip) is non-empty
```

These two snippets have not been compiled either.

### Incompatibilities in Annex C

The new tokens break two kinds of extremely rare old code:

<div class="compare" markdown="1">

```cpp
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};
// ^^ is now one token: ill-formed
```

```cpp
struct [[using CC:]] C;
// :] is now one token: ill-formed
struct [[using DD: ]] D;  // OK
```

</div>

The left is in [[diff.cpp23.lex#1]], the right in [[diff.cpp23.dcl.dcl#3]]. In addition, `<meta>` became a new standard header name ([[diff.cpp23.library]]).

## Consequences

### Reflection values cannot reach run time

Reflections mean nothing at run time, so they must be kept at compile time. P2996R13's approach was **consteval-only types**: `info` and any type containing `info`, including `info*` and classes with `info` members, whose objects can only exist at compile time (§4.3.3).

This rule later ran into trouble. [[P4101R1]] records the example from [[CWG3150]]: whether a class is a consteval-only type depends on its members, and the class may still be incomplete.

```cpp
struct S;
void f(S*);    // #1
struct S {     // #2
  std::meta::info x;
};
```

Does the definition at `#2` retroactively make `#1` ill-formed? If `S` is a template specialization, deciding would also require instantiation, while lots of existing code relies on there being no instantiation at that point. P4101R1 changed the rule to judge by value; it has been adopted into the draft, and the paper's title states that it targets C++26. In the current draft, a **consteval-only value** ([[g:consteval-only-value]]) is a non-null reflection or a pointer to an immediate function ([[expr.const.const#1]]); an object containing such a value is called an **immediate object**, and can only be the object of a `constexpr` variable, a template parameter object, or an object whose lifetime lies entirely within one constant evaluation ([[expr.const.const#3]]). The two models differ on null reflections:

<div class="compare" markdown="1">

```cpp
// P2996R13: judged by type
std::meta::info null;      // ill-formed
auto f(std::meta::info) {} // ill-formed:
                           // must be consteval
auto r = ^^int;            // ill-formed
```

```cpp
// current draft: judged by value
std::meta::info null;      // OK: null reflection
auto f(std::meta::info) {} // OK
auto r = ^^int;            // ill-formed:
                           // not constexpr
```

</div>

Both sides come from P4101R1 §4.3 and have not been compiled. Objects that actually carry a reflection are rejected on both sides; only the reason changes from type to value.

### Compile-time cost

Reflection moves metaprogramming into the constant evaluator. Constant evaluation is interpreted, and its number of steps is limited by the implementation ([[topics/compile-time-programming]]). The value-based design avoids creating a type for every step, but traversing a large namespace and instantiating the loop body once per member still costs compile time. No implementation was available here, so no measurements are given.

### Implementation status

Homebrew Clang 23 does not support `^^`, consteval blocks or annotations, and has no `<meta>`, but it already supports `template for`. According to P2996R13 §2.3, EDG has an experimental implementation and Bloomberg has open-sourced a Clang fork (clang-p2996), both usable on Compiler Explorer; the paper says both are incomplete. The uncompiled examples above were written per the current draft, have not been checked against these implementations, and carry no verdict.

How to use reflection to generate compile-time registries is covered in [[patterns/factory-and-registration]].

## Questions

!!! question "1"
    The library function below wants to return all the data members the caller can access. What is wrong with it? How do you fix it?
    ```cpp
    consteval auto visible_members(std::meta::info cls) {
      return std::meta::nonstatic_data_members_of(
          cls, std::meta::access_context::current());
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`current()` represents the place where it appears in the source, which is `visible_members` itself ([[meta.reflection.access.context#5]]), not the caller. If the caller is a friend of `cls`, the friendship is lost here, and the result contains only the members `visible_members` can access. The right way is to make the `access_context` a parameter, and have the caller write `access_context::current()` at its own location and pass it in. This is exactly why [[P3547R1]] argued against implicit checking from the call site.
</details>

!!! question "2"
    Why doesn't `template for (constexpr auto e : std::meta::enumerators_of(^^E))` work, so that it needs to be wrapped in `std::define_static_array` first?

<details markdown="1">
<summary>Answer</summary>

When the loop variable is `constexpr`, the expansion statement stores the range in a `constexpr` variable ([[stmt.expand#5.2]]). The `std::vector` returned by `enumerators_of` allocated memory during constant evaluation, and that memory cannot outlive the evaluation, so it cannot initialize a `constexpr` variable. `define_static_array` copies the elements into an array with static storage and returns a `span` referring to it, which works ([[meta.define.static]]).
</details>
