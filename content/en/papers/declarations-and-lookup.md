---
title: Rewriting declarations and lookup (P1787)
summary: C++23's P1787R6 rewrote the wording for scopes and name lookup. What was wrong with the old wording, which concepts the new wording introduced, which behaviors actually changed and which rules were merely spelled out, and how compilers implement it today.
tags: name lookup, scope, proposal, DR, C++23
group: Core language
updated: 2026-10-19
---

!!! tldr
    - Up to C++20, the wording for scopes and name lookup was scattered over dozens of paragraphs, "scope" had two definitions, and many cases could only be settled by guesswork; dozens of related CWG issues had piled up and could not be fixed one at a time.
    - [[P1787R6]] rewrote [[basic.scope]] and [[basic.lookup]] as a whole: a scope is a region of program text, a declaration inhabits a scope and binds a name in its target scope, and lookup is composed of layered operations: single search, search, and unqualified search.
    - For the vast majority of code the meaning did not change. Most of the new wording turns what compilers already did into rules; where implementations disagreed, it picks the more consistent option.
    - A few corner cases really did change, for example where parameter types are looked up in a friend declaration with a qualified name, and that `p->X<0>::f()` in a template needs `template`. Clang 23 still follows the C++20 rules in both places.
    - It was adopted as a defect report (DR), so there is no Annex C compatibility entry, and compilers do not distinguish old and new rules by `-std=`.

## Why the old wording couldn't be fixed

In the code below (example one), what does `x` in `f` refer to?

```cpp run title="udir.cpp" error
namespace F { float x; }
namespace A {
  namespace I { int x; }
  using namespace I;
  using F::x;
  void f() {
    x = 0;      // error: ambiguous
    A::x = 1;   // OK: F::x
  }
}
```

The answer is that the first line is ambiguous and the second refers to `F::x`. The C++20 wording (taking [[N4861]] as the reference) does lead to this conclusion, but only by piecing together three rules: the using-declaration introduces a synonym in `A`; the using-directive makes the members of `I` appear, for unqualified lookup, as if declared in the nearest enclosing namespace that contains both the directive and `I`, which here is `A`; and qualified lookup of `A::x` has yet another rule: look at `A`'s own declarations first, and only go into nominated namespaces if nothing is found. The three rules are each written separately, and the reader has to work out how they relate.

This was common in the old wording. The introduction of [[P1787R6]] lists several fundamental problems:

- [basic.scope] defined "scope" in two ways: one as the part of a declarative region where a name is valid, and another implicit in the lookup rules ([[CWG554]], [[CWG2165]]).
- Many lookup rules applied to a whole stretch of program text, such as a *template-id* containing several names and a `<`, rather than to a single name.
- The global namespace was sometimes described as one declarative region and sometimes as several.
- Many rules only said to look up in the context of some construct, without saying from which point the lookup happens or which declarations are visible. Once modules arrived, the default assumption that only earlier declarations in the same translation unit are visible no longer held, and those rules became ambiguous.
- There was no uniform rule for whether two declarations of the same name redeclare one entity or declare two conflicting ones.

The result was dozens of related CWG issues accumulated over years. The paper judged that the vagueness of the wording itself prevented resolving them one by one, and chose to rewrite [basic.scope], [basic.lookup] and part of [temp.res] as a whole. According to the paper's count, this resolved 63 core language issues at once, plus 21 problems that had only been discussed on the mailing list.

## The new vocabulary

The core of the rewrite is a set of new definitions, all of which are now in [[basic.scope.scope]] and [[basic.lookup.general]]. Explanations of each are on those two pages; here is just a comparison of old and new:

| C++20 terminology | Since C++23 | Change |
|---|---|---|
| Declarative region, potential scope, scope | Scope ([[g:scope]]) | Only one meaning left: a region of the program, nested into a tree |
| Point of declaration | Locus ([[g:locus]]) | Belongs to a declaration, not to a name |
| A name is introduced into a declarative region | A declaration inhabits ([[g:inhabit]]) a scope and binds a name in its target scope ([[g:target-scope]]) | Inhabiting and targeting are separate, so special declarations such as friends and block-scope `extern` can be described directly |
| Friends are not found by lookup | A friend declaration does not bind a name | From a lookup special case to a property of the declaration |
| Visible, in scope | Precedes ([[g:precedes]]) a program point | Explicitly counts declarations imported from modules |
| Look up in the context of such-and-such | Lookup from a program point | Every lookup has a definite starting point |
| A using-declaration introduces a synonym | It is replaced by the declarations it names during a search | No longer produces a new declaration |

Lookup itself is split into layers of operations, each doing one thing:

1. **Single search** ([[g:single-search|single search]]): in one scope, find declarations that bind the name and precede the point of lookup ([[basic.lookup.general#3]]).
2. **Search** ([[g:search-in-scope|search]]): if the scope is a class and the single search finds nothing, merge the results from the base classes ([[class.member.lookup#1]]).
3. **Unqualified search** ([[g:unqualified-search|unqualified search]]): if the scope is a namespace, also search the namespaces nominated by the active using-directives; if nothing is found, continue in the parent scope ([[basic.lookup.unqual#2]]).
4. **Unqualified lookup** starts from the program point where the name appears and performs an unqualified search in the immediate scope ([[basic.lookup.unqual#3]]); **qualified lookup** performs a search in the lookup context ([[g:lookup-context]]) ([[basic.lookup.qual#3]]).

With the new rules, example one reads in a straight line. `x` is an unqualified name; an unqualified search goes outward from the body of `f`. On reaching `A`, `A` itself and `I` (nominated by an active using-directive and contained in `A`) are searched together; the using-declaration in `A` is replaced by `F::x`, so both `F::x` and `I::x` are found, which is ambiguous ([[basic.lookup.general#1]]). `A::x` is a qualified name; searching in `A` finds `F::x`, and by [[namespace.qual#1]] the nominated namespaces are only entered when nothing is found. Clang 23, under both `-std=c++20` and `-std=c++23`, reports `reference to 'x' is ambiguous` only on the `x = 0` line. The conclusion for this example did not change; the derivation did.

Another term added later is host scope: if a declaration inhabits a block scope, that block scope; otherwise its target scope. It is not in P1787R6 but was added to the draft afterwards; see [[basic.scope]].

## Design trade-offs

P1787 is not a new feature with alternative designs to choose from. Its trade-offs show up at two levels.

The first level is a full rewrite versus patching issues one by one. Most of the related issues are different manifestations of the same kind of problem: a rule doesn't say where to look or what is visible. Patching them one by one would only add more special cases to wording that was already hard to read. The paper chose to first define a set of concepts that covers every case, and then resolve the individual issues as consequences of those concepts. The cost was a very large change; the paper says many of the changes are editorial taken individually, but there were so many that CWG had to review them one by one.

The second level is which side to take on specific disagreements. The paper's principle: where compilers agree, write what they do as the rule; where compilers disagree, pick the option that makes the language more consistent. The specific choices include:

- **A using-declaration no longer introduces a declaration.** The old wording described `using F::x;` as declaring a synonym in the current scope. With modules this created a puzzle: is that synonym exported or not? The paper adopted a solution proposed on the core mailing list: during lookup, the using-declaration is directly replaced by the declarations it names ([[basic.lookup.general#3]]), and the question disappears.
- **Rules follow implementations.** Some old rules were generally not followed by compilers, and the paper simply removed them. For example, a using-declaration rule involved in [[CWG1960]], which the paper says is widely ignored by implementations and interacts subtly with other using-declarations.
- **Rules do not follow implementations.** In a class's complete-class context (places such as member function bodies and default arguments that can see the whole class), unrestricted lookup of later declarations is allowed. The paper kept this, noting that it differed from what compilers actually did for non-template classes at the time. Outside a complete-class context, if a later declaration would change the result of a lookup, the program is ill-formed, no diagnostic required; this restriction already existed in the old wording and is now in [[class.member.lookup#6]].
- **Names after `.` and `->` are uniformly treated as qualified names.** The old wording had a special dual-lookup rule for names after member access; the new wording classifies them as member-qualified names ([[g:member-qualified-name]]) and runs them through the same qualified lookup as `N::x`. This causes the behavior change in example three below ([[CWG1835]]).
- **Lookup in a friend declaration looks into just one more scope.** For example two below, CWG's position on [[CWG2370]] was to search only once in the nominated class or namespace, and fall back to ordinary unqualified lookup if nothing is found, rather than going all the way outward from that scope.

## Example two: friend declarations with qualified names (behavior change)

```cpp run title="friend.cpp" ok
namespace A {
  using F = float;
  void f(F);
}
namespace B {
  using F = short;
  class Y {
    friend void A::f(F);   // F is A::F (float)
  };
}
int main() {}
```

`friend void A::f(F);` intends to declare the existing `f(float)` in `A` a friend. The question is where the parameter type `F` is looked up: the friend declaration is written in `B::Y`, and `B` also has an `F`.

C++20's [basic.lookup.unqual] ¶10 only specified looking in the member function's class first for the case where the friend is a member function; all other cases, including the namespace member `A::f` here, were treated as unqualified names in the class granting friendship. So `F` finds `B::F`, i.e. `short`; there is no `f(short)` in `A`, and the declaration is ill-formed.

[[basic.lookup.unqual#6]] changes this: when the *declarator-id* of a friend declaration is a qualified name whose nested-name-specifier designates a class or namespace S, unqualified names appearing after that qualified name are first searched for once in S, and if not found, ordinary unqualified lookup follows. `F` finds `A::F` in `A`, and the declaration is well-formed. This matches how parameters are looked up when `A::f` is defined outside `A`, where `F` is also looked for in `A` first.

!!! impl "Compiler status"
    Clang 23 rejects this line under `-std=c++20`, `-std=c++23` and `-std=c++2c`, reporting `friend declaration of 'f' does not match any declaration in namespace 'A'`, i.e. it still resolves `F` to `B::F` per the C++20 rules. Writing `friend void A::f(A::F);` has the same meaning under old and new rules and passes in both modes. Testing with Example 2 of [[basic.lookup.unqual#6]] in the standard, Clang also continues into the enclosing scopes of S when S is a class: `friend void W::X::g(D);` finds `W::D` (`void`) and errors, while `friend void W::X::g(I);` finds `::I` (`int`) and passes; both are the opposite of the current draft's verdict.

## Example three: `<` after member access (behavior change)

<div class="compare" markdown="1">

```cpp title="OK in C++20" error
struct A { void f() {} };
template<int> using X = A;

template<class T>
void g(T* p) {
  p->X<0>::f();  // error (C++23)
}
template void g(A*);
```

```cpp title="OK under both rules" ok
struct A { void f() {} };
template<int> using X = A;

template<class T>
void g(T* p) {
  p->template X<0>::f();
}
template void g(A*);
```

</div>

`p->X<0>::f()` qualifies the member `f` with a namespace-scope alias template `X<0>`. When the compiler parses the `<` after `X`, it has to decide whether it starts a template argument list or is a less-than sign.

C++20's [basic.lookup.classref] had a dedicated rule for this: when `.` or `->` is followed by an identifier and `<`, the identifier is first looked up in the class of the object expression, and if not found, in the context of the entire postfix expression. The type of `*p` depends on `T`, so the first step cannot be performed; the second step finds `::X`, so `<` starts a template argument list, and the left side compiles.

The new wording deleted this special rule. `X` is a member-qualified name whose lookup context is a dependent type, so by [[basic.lookup.qual#3]] no lookup is done at the point of definition; it is not an unqualified name either, so no unqualified lookup is done. By [[temp.names#7]], without the `template` keyword and with no template found by lookup, `<` is a less-than sign, and the whole expression is parsed as `((p->X) < 0) > ::f()`. When `g<A>` is instantiated, `A` has no member `X`, and the program is ill-formed. To express the original meaning you must write `p->template X<0>::f()`; Example 3 of [[basic.lookup.qual]] walks through these cases line by line.

If the object expression is not dependent, as in `void h(A* p) { p->X<0>::f(); }`, then when `X` is not found in `A` the lookup falls back to unqualified lookup and finds `::X`, which is well-formed under both old and new rules. The change only shows up in templates.

!!! impl "Compiler status"
    Clang 23 accepts the code on the left under `-std=c++20`, `-std=c++23` and `-std=c++2c` without a warning, still following the C++20 rules.

## What actually changed

For everyday code, P1787 is almost transparent. It changed how the rules are written, not what most programs mean:

- For ordinary code like example one, the old and new wording give the same answer; the new wording just has a single derivation path.
- Some issues were resolved by writing into the standard what compilers had long been doing. For example, the restriction in [[CWG110]] was downgraded to a note, and the paper states that this matches the behavior of GCC, Clang and ICC.
- The real changes in meaning are corner cases like examples two and three.
- There is one new deprecation: writing a class template or alias template name after the `template` keyword without a template argument list, as in `N::template X` (for example as a template template argument), is deprecated ([[depr.template.template]]). Clang 23 gives no deprecation warning for `S<N::template X>` under `-std=c++23`.

There is no entry in [[diff.cpp20]] corresponding to P1787. The reason is that it was handled as a defect report: the committee considered the new wording to express what had always been intended, so it applies to earlier standard modes as well, and compilers do not switch between old and new behavior by `-std=` (for what a DR means, see [[papers/how-to-read-a-paper]]). The tests above bear this out: Clang behaves identically in C++20 and C++23 modes.

As for implementation progress, GCC's C++ status page marks P1787R6 as a DR, not yet implemented; the C++23 table on Clang's C++ status page does not list this paper. Judging from the examples above, the parts where Clang 23 already conforms to the new rules are mainly those where the new rules copied existing practice in the first place.

For the template-side changes that accompanied this rewrite, such as the term member of an unknown specialization being replaced by dependent qualified names, see [[temp.dep]] and [[topics/two-phase-lookup]]; for the design of ADL and customization points, see [[topics/name-lookup-and-customization]].

## Questions

!!! question
    In example two, delete `using F = float;` from `namespace A`. What does `F` in `friend void A::f(F);` find under the current draft? If `A` only declares `void f(float);`, is this line still well-formed?

<details markdown="1">
<summary>Answer</summary>

Searching for `F` in `A` finds nothing, so by [[basic.lookup.unqual#6]] it falls back to unqualified lookup starting from the friend declaration, going through `Y` and then `B`, and finds `B::F`, i.e. `short`. There is no `f(short)` in `A`, so this friend declaration does not correspond to any declaration in `A` and is ill-formed. Here the old and new rules reach the same conclusion.
</details>

!!! question
    `template<class T> void g(T t) { t.foo<0>(); }`, where `foo` is a member function template of `T`. Why must you write `t.template foo<0>()` here? How is this different from example three?

<details markdown="1">
<summary>Answer</summary>

`foo` is a member-qualified name whose lookup context `T` is dependent, so no lookup happens at the point of definition ([[basic.lookup.qual#3]]), and `<` can only be parsed as less-than ([[temp.names#7]]); hence `template` is required. This requirement existed in C++20 too: the second step of the old rule only looked in the enclosing context, where `foo` is not found, so `<` could not be taken as the start of a template argument list either. The difference in example three is that the enclosing scope happens to have a `::X` with the same name, which the special C++20 rule used to decide the meaning of `<`; the new rules no longer do that.
</details>
