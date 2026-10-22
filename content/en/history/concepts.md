---
title: Thirty years of concepts
summary: Why templates went so long without interfaces, why C++0x concepts were pulled in 2009, and what design C++20 adopted instead; today's rules for satisfaction, subsumption and `Concept auto` are what those trade-offs left behind.
tags: concepts, constraints, generic programming, SFINAE, history of standardization
updated: 2026-10-19
---

!!! tldr
    - C++98 templates had no interfaces: requirements on template arguments lived only in documentation, and errors surfaced deep inside instantiation. Constraints classes and `enable_if` were library authors' workarounds.
    - The first version of concepts, in C++0x, made a concept a set of function signatures. Types declared that they met a concept through concept maps, and function bodies were checked against the constraints. The specification grew, compilation slowed down, and no agreement could be reached; the whole feature was pulled in 2009.
    - C++20 concepts are compile-time predicates: the compiler computes whether a type satisfies a concept, the relative strength of concepts is derived from the logical structure of their constraints, and function bodies are not definition-checked.
    - Subsumption only recognizes atomic constraints that come from the same place in the source, so to make one concept stronger than another, its definition must name that other concept.
    - The `auto` in `void f(Sortable auto&)` is a compromise from a fight over syntax. C++26 makes fold-expression constraints comparable for strength and allows concepts to be passed as template arguments.

The historical material on this page comes mainly from three retrospectives by Stroustrup: *The Design and Evolution of C++* (1994, D&E below), the HOPL III paper *Evolving a language in and for the real world: C++ 1991–2006* (2007) and the HOPL IV paper *Thriving in a Crowded and Changing World: C++ 2006–2020* (2020). They are one participant's recollections; where they describe other people's views or the mood of a meeting, the text says "according to Stroustrup". The rules themselves are in [[temp.constr]], [[temp.concept]], [[expr.prim.req]] and [[topics/concepts]].

## Templates without interfaces

### Two out of three goals

Looking back, Stroustrup says he wanted three things from templates: enough generality; zero overhead compared with hand-written code; and well-defined interfaces, with type checking and overloading as good as for ordinary functions (HOPL IV §6.1). Nobody knew then how to get all three at once, and C++ got the first two.

The result was that template interfaces became compile-time duck typing: whatever operations a template uses on its argument, the argument has to support, but those requirements are not written in the declaration. The standard library's requirements ("input iterator", "less-than comparable") lived only in requirement tables in the standard's text; as HOPL III §8.3.3 puts it, "compilers don't read manuals". Get it wrong and the error message points at some line inside the template, often several screens long.

Why not do what Eiffel does and require the argument to derive from some base class, written `template<class T : Base>`? In [[N1510]] (2003), Stroustrup says signature-based schemes of this kind had been considered, and rejected, many times since around 1986. They require the signatures of the argument type's operations to match the contract exactly, and they cannot handle implicit conversions, overloading or mixed-type arithmetic, which are everyday matters in C++ generic code.

### Two workarounds from library authors

The first was the **constraints class**: write a class template that exercises each required operation once, then instantiate it at the start of the algorithm so that errors show up at the entry point. Boost's Concept Check Library made this technique systematic (HOPL III §8.3.3).

```cpp run title="constraints_class.cpp" ok
// C++98 style: instantiating Forward_iterator<T> fails if T lacks these operations
template<class T> struct Forward_iterator {
    static void constraints(T a) {
        ++a; a++;          // can be incremented
        T b = a; b = a;    // can be copied
        *b = *a;           // can be dereferenced and assigned
    }
    Forward_iterator() { void (*p)(T) = constraints; (void)p; }
};

template<class In, class Pred>
In find_if2(In first, In last, Pred pred) {
    Forward_iterator<In>();                 // checked at the start of the body
    while (first != last && !pred(*first)) ++first;
    return first;
}

bool even(int x) { return x % 2 == 0; }
int main() { int a[] = {1, 2, 3}; return *find_if2(a, a + 3, even) == 2 ? 0 : 1; }
```

The check is in the function body, invisible to callers, and it cannot take part in overload resolution. It only makes errors appear a bit earlier and a bit shorter.

The second used [[g:sfinae]]: if substituting template arguments into a function template declaration produces an invalid type or expression, that candidate is simply discarded, not treated as an error. In 2003 Järvi, Willcock, Lumsdaine and others packaged this as `enable_if` (*Concept-controlled polymorphism*, GPCE 2003), and C++11 added it to the standard library. It can take part in overload resolution, but the conditions of two overloads have to be written by hand to be mutually exclusive. Below, the left side uses `enable_if` and the right side is the C++20 version:

<div class="compare" markdown="1">

```cpp run ok
#include <iterator>
#include <list>
#include <type_traits>
template<class It>
using cat = typename
  std::iterator_traits<It>::iterator_category;
template<class It>
constexpr bool is_ra = std::is_base_of_v<
  std::random_access_iterator_tag, cat<It>>;

template<class It,
         std::enable_if_t<is_ra<It>, int> = 0>
void my_advance(It& it, int n) { it += n; }

template<class It,
         std::enable_if_t<!is_ra<It>, int> = 0>
void my_advance(It& it, int n)
{ while (n--) ++it; }   // conditions must be mutually exclusive

int main() {
  int a[4]{}; int* p = a;
  my_advance(p, 2);
  std::list<int> l{1, 2, 3};
  auto i = l.begin(); my_advance(i, 2);
}
```

```cpp run ok
#include <iterator>
#include <list>

template<std::random_access_iterator It>
void my_advance(It& it, int n) { it += n; }

template<std::input_iterator It>
void my_advance(It& it, int n)
{ while (n--) ++it; }
// when both are satisfied, the more constrained
// one wins; no hand-written exclusive conditions

int main() {
  int a[4]{}; int* p = a;
  my_advance(p, 2);
  std::list<int> l{1, 2, 3};
  auto i = l.begin(); my_advance(i, 2);
}
```

</div>

On the left the constraint is hidden in a default template argument, and someone reading the declaration has a hard time seeing what it requires. In 2016 Ville Voutilainen listed these problems one by one in [[P0225R0]] as reasons to bring in concepts soon. The right side works because of the C++20 subsumption rules ([[temp.constr.order]]): the definition of `random_access_iterator` names `bidirectional_iterator`, which in turn names `forward_iterator` and `input_iterator`, so it is more constrained than `input_iterator`. Where that rule came from is covered below.

## The first attempt: C++0x concepts (2003–2009)

### Two approaches

In 2003 Stroustrup and Gabriel Dos Reis proposed describing constraints with **use patterns**: listing the expressions that should be valid for a type, rather than listing function signatures ([[N1510]] and others). At almost the same time, Douglas Gregor, Jeremy Siek, Andrew Lumsdaine and others at Indiana University proposed a different design ([[N1758]]). Their differences can be summarized in a table (HOPL IV §6.2):

| | Indiana design | Texas design |
|---|---|---|
| What a concept is | A set of operations (pseudo-signatures) and associated types, similar to Haskell type classes | A compile-time type predicate, described by use patterns |
| How a type satisfies a concept | Declared explicitly by the programmer | Computed by the compiler |

The committee encouraged a merger rather than a contest, and in 2006 the two groups wrote the joint proposal [[N2081]]. According to HOPL IV, the merged design was mostly the Indiana design, because its implementation (ConceptGCC, Gregor's prototype on GCC) was far ahead. In September 2008 the wording paper [[N2773]] went into the C++0x working draft, together with a whole set of papers adding concepts to the standard library.

### What it looked like

This is how C++0x concepts were written (per HOPL IV §6.2 and [[N2773]]). This syntax never made it into a published standard, and today's compilers do not accept it.

```cpp
// historical syntax (C++0x concepts), not valid C++
concept EqualityComparable<typename T> {          // concept = a set of operations
    bool operator==(const T& x, const T& y);
    bool operator!=(const T& x, const T& y) { return !(x == y); }
}

concept BidirectionalIterator<typename Iter>      // explicit refinement
    : ForwardIterator<Iter> { /* ... */ }

concept_map EqualityComparable<int> {}            // explicitly declare that int satisfies the concept

template<class T>
concept_map ForwardIterator<T*> {                 // supply the associated type for T*
    typedef T value_type;
}

auto concept LessThanComparable<typename T> {     // auto: allow automatic matching
    bool operator<(const T&, const T&);
}

template<typename T>
    requires LessThanComparable<T>
const T& min(const T& x, const T& y) { return x < y ? x : y; }
```

It contains four designs that were all later abandoned:

- A **concept map** explicitly declared how a type satisfied a concept, and could also supply missing operations or types. `int*` has no member `value_type`; `concept_map ForwardIterator<T*>` supplied it. The Indiana side held that explicit declarations prevent misuse where a type matches syntactically by accident but is semantically unrelated; the Texas side held that concept maps that add no functionality are just a burden. The compromise was `auto concept`, letting the concept's author decide whether it could be matched automatically (HOPL IV §6.2.3).
- **Explicit refinement**: building a concept hierarchy level by level with `: ForwardIterator<Iter>`, like class derivation. HOPL IV §6.2.1 considers this rigid; real-world concepts often do not form strict hierarchies.
- **Definition checking**: the body of a constrained template was checked against its constraints, and using an operation not in the constraints was an error. To be able to call old templates that had no constraints yet, a `late_check` block was added, inside which checking was turned off (HOPL IV §6.2.4).
- **Axioms**: semantic properties written in a concept, such as transitivity of a total order. Compilers could use them as assumptions but did not verify them ([[N2887]]).

### Why it was pulled

HOPL IV §6.2.6 lists the problems that had accumulated by 2009. They fall into three groups:

- No agreement. There was never consensus on whether concept maps should generally be required, or whether refinement should be declared or deduced.
- The specification was too big. The core language part was about 91 pages, and describing the standard library took about 125 concepts.
- Implementation cost was high. A compiler with concepts was more than 10 times slower than one without; there were still examples where constrained code produced worse machine code than unconstrained templates. Combining concept maps with `late_check` could also give the same type inconsistent views at different points in a program.

There was a more fundamental difficulty as well. Writing concepts as signatures with concrete types means deciding whether parameters are passed by value, by `const&` or by `&&`, and whether it is `x.f(y)` or `f(x, y)`. Each extra parameter multiplies the number of combinations, and the burden of matching ends up on type authors and concept map authors (HOPL IV §6.2.1).

In spring 2009 a discussion on the mailing list brought the problem into the open: for one standard library component, if it were implemented according to one particular design, ordinary users would have to write concept maps themselves (introduction of [[N2906]]). Stroustrup then wrote [[N2906]], arguing that all concepts should be matched automatically so that concept maps would become rare. His argument: a nominal type system catches errors through explicit declarations, while a structural type system lets things be used interchangeably when their structure matches; templates are structural by nature, which is why generic programming succeeded in C++, and the design at the time had leaned too far towards the nominal end for the sake of safety. There were also proposals at the time going the opposite way, insisting on explicit modeling.

In July 2009 the committee decided to remove concepts from C++0x (HOPL IV §6.2; Herb Sutter's trip report that month). Sutter described it as a trade-off for the schedule: the design was still changing, so the rest of the features should ship on time first. In *The C++0x "Remove Concepts" Decision*, published in Dr. Dobb's, Stroustrup said he would have preferred to fix the design and then ship, but given a choice between removal and keeping it as it was, he too voted for removal.

## The second design: concepts as predicates (2009–2016)

### Starting over from the user's side

After the removal, Stroustrup, Dos Reis and Andrew Sutton started a new design (HOPL IV §6.3). In 2011 Alex Stepanov convened a week-long meeting that asked, from the user's point of view: what should a properly constrained set of STL algorithms look like? The result was [[N3351]] *A Concept Design for the STL* (2012). According to Stroustrup, today's way of listing expressions in a `requires` expression was proposed at that meeting, building on the use patterns of 2003 (HOPL IV §6.3.3).

The 2013 paper [[N3580]] *Concepts Lite* summarized the new design: constrain template arguments with predicates; constraints guarantee that a template is used correctly, not that it is defined correctly; support overloading based on constraints; no run-time overhead. Compared with C++0x concepts:

| | C++0x concepts | Concepts Lite onward |
|---|---|---|
| What a concept is | A set of pseudo-signatures and associated types | A compile-time predicate |
| How a type satisfies a concept | Concept map, or `auto concept` | Always computed by the compiler |
| Relative strength of concepts | Explicit refinement | Derived from the logical structure of constraints |
| Template definitions | Checked against constraints | Not checked |
| Axioms | Yes | No |

Today [[temp.constr.atomic#3]] says an atomic constraint is satisfied if the expression after substitution is `true`. No declaration can make a type satisfy or not satisfy a concept; that is how the explicit-versus-implicit fight of C++0x ended.

### The trade-off of no definition checking

Leaving out definition checking was the most controversial decision. The designers estimated that about 90% of the benefit came from checking at the point of use, and that authors of constrained templates were mostly experts (HOPL IV §6.3.1). Stroustrup also listed practical benefits of not checking definitions:

- Early in development the requirements are often incomplete, and partial constraints can be used in the meantime;
- With definition checking, adding a line of debug output or statistics code to a function would mean changing the constraints first;
- Constrained templates can call old unconstrained templates, so old code can be migrated gradually.

Opponents were worried about the future. In [[P0240R0]] (2016), Matt Calabrese cited Douglas Gregor's view that putting concepts into the standard without definition checking meant definition checking could never be added later. That concern still holds: constrained templates today are still checked by the C++98 two-phase rules ([[temp.res]], [[topics/two-phase-lookup]]), and constraints only decide whether a template can be selected, not which operations its body may use.

```cpp run title="no_definition_check.cpp" ok
#include <iterator>

template<std::forward_iterator I>
void advance_by(I& p, int n) {
    p += n;   // += is not in the constraint; no error at the definition
}
// the error only appears when instantiated with a std::list iterator
```

HOPL IV §6.3.1 uses this same example. Stroustrup's position is that if definition checking is added in the future, a way to bypass it must be provided at the same time, and C++0x's `late_check` was not enough.

### The Concepts TS and its syntax

The design was first published as a Technical Specification: ISO/IEC TS 19217:2015 *C++ Extensions for Concepts*, implemented in GCC 6 under `-fconcepts`. The TS had several forms that were later removed:

```cpp
// historical syntax (Concepts TS), not valid C++20
template<typename T>
concept bool Sequence = Has_begin<T> && Has_end<T>;   // variable form, bool required

template<typename T>
concept bool Sortable() { return /* ... */; }         // function form, used as Sortable<T>()

void sort(Sortable& c);                               // natural syntax: the concept name used as a type;
                                                      // the function automatically becomes a template
Mergeable{In1, In2, Out}                              // template introduction
Out merge(In1, In1, In2, In2, Out);
```

`concept bool` came about because Concepts Lite initially made concepts `constexpr` functions returning `bool`, and once C++14 had variable templates, a variable form was allowed too. With both forms around, users had to remember which form each concept used to know whether to write parentheses (HOPL IV §6.3.6).

In early 2016 the committee discussed merging the TS into C++17, and the motion failed. The objections that can be confirmed from the papers fall into three groups: the lack of definition checking and what that meant for the future, the lack of a conceptified standard library ([[P0240R0]]), and the TS having been published less than a year earlier, with too little implementation and usage experience (Sutter's March 2016 trip report).

## C++20: what was removed and what remained

### Concepts become first-class entities

In 2017, [[P0587R0]] (Richard Smith, James Dennett) pointed out that concepts are always boolean, so `concept bool` is redundant, and that modeling concepts as functions or variables leaks implementation details into the interface (`C<X>` or `C<X>()`), and even makes it possible to take the address of a concept. [[P0734R0]], merged into the C++20 draft the same year, adopted these points, leaving concepts with a single form:

<div class="compare" markdown="1">

```cpp
// Concepts TS
template<typename T>
concept bool Sortable() { ... }

template<typename T>
  requires Sortable<T>()
void sort(T&);
```

```cpp
// C++20
template<typename T>
concept Sortable = ...;

template<typename T>
  requires Sortable<T>
void sort(T&);
```

</div>

That is why today a concept can only be defined at namespace scope, cannot have associated constraints, is never instantiated, and cannot be specialized ([[temp.concept#3]]–[[temp.concept#5]]). It no longer borrows the shell of a function template or variable template.

### Why subsumption only recognizes source locations

The TS decided whether two atomic constraints were identical by comparing their token sequences, and it broke constraints down all the way into each requirement inside a `requires` expression. [[P0587R0]] and [[P0717R1]] by Smith and Sutton pointed out that this was both expensive and fragile: two concepts in different namespaces, spelled the same but meaning different things, would be treated as equivalent, and a harmless refactoring could change the result of overload resolution.

The model proposed in [[P0717R1]] was that two atomic constraints can only be identical if they come from the same place in the source. That became today's [[temp.constr.atomic#2]], and at the same time a `requires` expression as a whole counts as a single atomic constraint. The consequence is that to make one concept stronger than another, its definition must name that other concept:

<div class="compare" markdown="1">

```cpp run error
template<class T> concept HasF =
  requires(T t) { t.f(); };
template<class T> concept HasFG =
  requires(T t) { t.f(); t.g(); };

template<class T> requires HasF<T>
int pick(T) { return 1; }
template<class T> requires HasFG<T>
int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});
// error: ambiguous. Each requires expression
// is one atomic constraint; neither subsumes the other
```

```cpp run ok
template<class T> concept HasF =
  requires(T t) { t.f(); };
template<class T> concept HasFG =
  HasF<T> && requires(T t) { t.g(); };

template<class T> requires HasF<T>
int pick(T) { return 1; }
template<class T> requires HasFG<T>
int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});  // OK: picks the second
int main() { return x == 2 ? 0 : 1; }
```

</div>

C++0x declared refinement with `: ForwardIterator<Iter>`; C++20 has no refinement syntax. Refinement is just conjoining another concept with `&&` in the definition, which normalization ([[temp.constr.normal]]) expands and the subsumption rules ([[temp.constr.order]]) then reason about. This is still the compiler computing relationships between concepts, only the basis has narrowed from semantics to source structure. The `my_advance` example in the first section works precisely because the standard library's iterator concepts are written this way, naming each level.

### The abbreviated syntax: why `Sortable auto&`

The TS's natural syntax `void sort(Sortable& c)` did not go into C++20 with [[P0734R0]]. Tom Honermann's [[P0696R1]] pointed out its problem: whether `void f(X x)` is a template depends on whether `X` is a type or a concept. That difference affects forwarding references, whether a `static` variable in the function exists once per instantiation, and whether the definition can live outside a header, yet neither a reader nor a diff tool can see it. Stroustrup's [[P0694R0]] defended it, arguing that it was the simplest notation for about two thirds of the STL algorithms.

Over the next two years a batch of mutually incompatible alternative syntaxes appeared. [[P1141R2]] (2018), co-authored by the authors of several earlier proposals, gave the rule: anywhere `auto` can be written, `Concept auto` can be written, meaning deduce as with `auto` and additionally check the constraint.

<div class="compare" markdown="1">

```cpp
// Concepts TS: you can't tell that f is a template
void sort(Sortable& c);
Sortable x = make();
```

```cpp
// C++20: auto marks the deduction
void sort(Sortable auto& c);
Sortable auto x = make();
```

</div>

Stroustrup supported this compromise, but in HOPL IV §6.4 he wrote that he considers the `auto` after the concept name redundant. Template introduction, `Mergeable{In1, In2, Out}`, did not regain consensus.

[[P1141R2]] also specified that `T` in `template<C T>` is always a type parameter, and that `template<C... T>` means `(C<T> && ...)` rather than `C<T...>`. So C++20 has four ways to constrain a function template. To a caller they have the same effect, but as declarations they are not equivalent and cannot be mixed to redeclare the same template ([[temp.over.link]]):

```cpp run title="four_forms.cpp" ok
#include <concepts>

template<class T> concept Sortable = requires(T& c) { c.begin(); c.end(); };

template<class C> requires Sortable<C> void sort1(C&);   // requires-clause
template<Sortable C> void sort2(C&);                     // type-constraint
template<class C> void sort3(C&) requires Sortable<C>;   // trailing requires-clause
void sort4(Sortable auto&);                              // abbreviated function template

std::integral auto twice(std::integral auto x) { return x * 2; }   // also works for return types

int main() { std::integral auto n = twice(21); return n == 42 ? 0 : 1; }
```

Compound requirements were settled in the same period. [[P1084R2]] specified that `{ E } -> C<Args>;` means `C<decltype((E)), Args>`; [[P1452R2]] removed the `{ E } -> Type;` form, which meant implicitly convertible to `Type`, a meaning inconsistent with `-> Concept`. Today you write `-> std::same_as<int>` or `-> std::convertible_to<int>` and say what you mean ([[expr.prim.req]]).

### Library concepts: satisfying and modeling are different things

The standard library concepts came out of the Ranges work and were added to `<concepts>` in 2018 by [[P0898R3]] *Standard Library Concepts*. They were originally named in CamelCase (`ForwardIterator`); [[P1754R1]] in 2019 renamed them all to standard library style, like `forward_iterator`. One motivation recorded in HOPL IV §6.5 was that the CamelCase names had started to clash with identifiers in other libraries.

The axioms of C++0x left a trace in the library concepts. Syntactically **satisfying** a concept and semantically [[g:models-concept|modeling]] it are different things: modeling also requires meeting the semantic requirements in the specification, such as equality preservation in [[concepts.equality]]. The compiler checks only satisfaction; if a program depends on modeling and a template argument satisfies a concept without modeling it, the program is ill-formed, no diagnostic required ([[res.on.requirements#2]]). This is the same role axioms had: they may be used as assumptions, but the compiler does not verify them.

## C++26: two additions

### Fold-expression constraints can be ordered

In C++20, a fold expression such as `(C<Ts> && ...)` is a single atomic constraint, and two such constraints cannot be compared for strength. Corentin Jabot's [[P2963R3]] introduced [[g:fold-expanded-constraint|fold expanded constraints]]: during normalization a fold expression becomes a new kind of constraint, satisfaction is checked element by element ([[temp.constr.fold]]), and subsumption can compare through it ([[temp.constr.order#1]]).

```cpp run title="fold_expanded.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
int g(Ts...) { return 1; }

template<class... Ts> requires (std::signed_integral<Ts> && ...)
int g(Ts...) { return 2; }

int main() { return g(1, 2) == 2 ? 0 : 1; }   // C++26: picks the second
```

Compiled with `clang++ -std=c++20`, Clang reports the call as ambiguous; with `-std=c++2c` it picks the second overload.

### Concepts as template arguments

C++20 concepts cannot be passed as template arguments; to write a concept meaning "all of these types satisfy some concept", you had to write it out once for each concept. [[P2841R7]] allows a template parameter to itself be a concept or a variable template (syntax in [[temp.param]]). When a concept name in a constraint depends on a template parameter, normalization can only expand it once the concept is known; such a constraint is called a [[g:concept-dependent-constraint]] ([[temp.constr.normal#1]]).

```cpp run title="concept_tparam.cpp" ok
#include <concepts>

template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long>);
static_assert(!all_satisfy<std::integral, int, double>);

int main() {}
```

## Traces in today's rules

| Today's rule | Where | Origin |
|---|---|---|
| A type satisfies a concept without any declaration | [[temp.constr.atomic#3]] | The C++0x fight over concept maps; [[N2906]] argued for automatic matching everywhere |
| No dedicated refinement syntax; strength derived from constraint structure | [[temp.constr.normal]], [[temp.constr.order]] | C++0x's explicit refinement was considered too rigid |
| Atomic constraints are identical only if they come from the same place in the source; `requires` expressions are not broken down | [[temp.constr.atomic#2]] | Criticism of the TS's token comparison in [[P0587R0]] and [[P0717R1]] |
| Concepts have a single form of definition and cannot be specialized or constrained | [[temp.concept]] | The TS's function form and `concept bool` were removed |
| Bodies of constrained templates are not checked against their constraints | [[temp.res]] | Concepts Lite deliberately deferred definition checking |
| Abbreviated function templates must write `C auto` | [[dcl.fct#23]] | The fight over the natural syntax and the [[P1141R2]] compromise |
| `{ E } -> C<Args>` means `C<decltype((E)), Args>`; there is no `-> Type` | [[expr.prim.req]] | [[P1084R2]], [[P1452R2]] |
| A library concept satisfied but not modeled leads to IFNDR | [[res.on.requirements]] | Semantic requirements, like C++0x axioms, are not verified by the compiler |
| Fold-expression constraints take part in subsumption | [[temp.constr.fold]] | C++26, [[P2963R3]] |
| A concept name in a constraint can be a template parameter | [[temp.constr.normal]] | C++26, [[P2841R7]] |

## Timeline

| Year | Event |
|---|---|
| Around 1987 | Stroustrup tries to design interfaces for templates, without success (HOPL IV §6.1) |
| 2003 | Use-pattern concept design ([[N1510]]); `enable_if` published |
| 2006 | Indiana and Texas designs merged ([[N2081]]) |
| 2008 | C++0x concepts merged into the working draft ([[N2773]]) |
| 2009 | Concepts removed from C++0x |
| 2013 | Concepts Lite ([[N3580]]) |
| 2015 | Concepts TS published |
| 2016 | Not merged into C++17 |
| 2017 | Merged into the C++20 draft after dropping `bool`, the function form and the natural syntax ([[P0734R0]]) |
| 2018 | `Concept auto` abbreviated syntax ([[P1141R2]]); standard library concepts ([[P0898R3]]) |
| 2019 | Library concepts renamed to standard_case ([[P1754R1]]) |
| 2020 | C++20 published |
| 2024–2025 | Fold expanded constraints ([[P2963R3]]); concept template parameters ([[P2841R7]]), both in C++26 |

## Open problems

There is still no definition checking. As of October 2026, the WG21 paper index has no proposal under consideration whose subject is definition checking for constrained templates.

Diagnostic quality is another ongoing topic, for example [[P2429R0]] *Concepts Error Messages for Humans* (2022). The standard only specifies whether a program is well-formed; the form of diagnostics is up to the implementation, so improvements of this kind mostly happen in compilers.

## References

- Bjarne Stroustrup. *The Design and Evolution of C++*. Addison-Wesley, 1994. §15.4.
- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §8.3.3.
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL, 2020. §6.
- Bjarne Stroustrup. *The C++0x "Remove Concepts" Decision*. Dr. Dobb's, July 2009.
- Herb Sutter. *Trip Report: Exit Concepts, Final ISO C++ Draft in ~18 Months*. 2009-07-21; and the winter meeting report of 2016-03-11.
- [[N1510]] Stroustrup, *Concept checking – A more abstract complement to type checking*, 2003.
- [[N2773]] Gregor, Stroustrup, Widman, Siek, *Proposed Wording for Concepts (Revision 9)*, 2008.
- [[N2906]] Stroustrup, *Simplifying the use of concepts*, 2009.
- [[N3580]] Sutton, Stroustrup, Dos Reis, *Concepts Lite: Constraining Templates with Predicates*, 2013.
- [[P0240R0]] Calabrese, *Why I want Concepts, but why they should come later rather than sooner*, 2016.
- [[P0587R0]] Smith, Dennett, *Concepts TS revisited*; [[P0717R1]] Smith, Sutton, *Semantic constraint matching for concepts* (2017).
- [[P0696R1]] Honermann, *Remove abbreviated functions and template-introduction syntax from the Concepts TS*, 2017.
- [[P1141R2]] Voutilainen et al., *Yet another approach for constrained declarations*, 2018.
- [[P2963R3]] Jabot, *Ordering of constraints involving fold expressions*, 2024.
- [[P2841R7]] Jabot, Ažman, Touton, Tong, *Concept and variable-template template-parameters*, 2025.
