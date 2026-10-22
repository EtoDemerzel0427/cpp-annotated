---
title: Templates
summary: "A guide to Clause 13: how templates are declared, given arguments and constrained, how names inside templates are looked up, when specializations are generated, how function template arguments are deduced, and which page covers each part."
updated: 2026-10-19
---

!!! tldr
    - A template is a rule for generating a family of entities; its specializations are the actual classes, functions or variables: `std::vector<int>` is a class, `std::vector` is not.
    - Constructs in a template are either dependent (they depend on template parameters) or non-dependent. Non-dependent parts are checked at the definition, dependent parts are deferred to instantiation. This is two-phase lookup, and it is why you have to write `typename` and `template`.
    - This clause has many IFNDR rules, because the same template is expanded in several translation units and at several points of instantiation, which the compiler cannot compare against each other.
    - Suggested order: [[temp.pre]] → [[temp.param]] → [[temp.names]] → [[temp.arg]], then constraints, name resolution, instantiation and deduction as needed.

```cpp run ok
#include <concepts>
template<std::integral T>          // template parameter and constraint (13.2, 13.5)
T twice(T x) { return x + x; }     // function template (13.1, 13.7)

template<class T>
struct Box {
  T v;
  typename T::size_type n() const  // a dependent name needs typename (13.8)
  { return v.size(); }
};

int main() {
  auto a = twice(21);              // deduces T = int (13.10), implicitly instantiates twice<int> (13.9)
  // twice(1.5);                   // error: double does not satisfy std::integral
  return a - 42;
}
```

This snippet uses almost every part of Clause 13: declaring a template, supplying template arguments, checking constraints, looking up names in a template, instantiating specializations, deducing template arguments. The clause explains how each of these steps works. It borrows heavily from name lookup ([[basic.lookup]]), the ODR ([[basic.def.odr]]), constant expressions ([[expr.const]]) and overload resolution ([[over.match]]), and adds the dependent/non-dependent distinction on top of them.

## Structure of the clause

| Subclause | Content | Page on this site |
|---|---|---|
| 13.1 | Parts of a template declaration, templated entities, *requires-clause*, reachability of definitions | [[temp.pre]] |
| 13.2 | Template parameters: type parameters, constant parameters, template template parameters; default arguments; parameter packs | [[temp.param]] |
| 13.3 | *template-id*: when `<` starts a template argument list, the `template` keyword, `>>` | [[temp.names]] |
| 13.4 | How each kind of template argument is matched to its parameter | [[temp.arg]] |
| 13.5 | Constraints: forms, satisfaction, normalization, ordering by constraints | [[temp.constr]], [[temp.constr.order]] |
| 13.6 | When two *template-id*s denote the same type | [[temp.type]] |
| 13.7 | Class templates and their members, variadic templates, friends, partial specializations, overloading and partial ordering of function templates, alias templates, concepts | [[temp.decls]], [[temp.class]], [[temp.spec.partial]], [[temp.fct]], [[temp.alias]], [[temp.concept]], and others |
| 13.8 | Name resolution: dependent names, dependent types and expressions, two-phase lookup, points of instantiation | [[temp.res]], [[temp.dep]], [[temp.dep.res]] |
| 13.9 | Implicit instantiation, explicit instantiation, explicit specialization | [[temp.spec]], [[temp.inst]], [[temp.explicit]], [[temp.expl.spec]] |
| 13.10 | Explicit template arguments, template argument deduction (where SFINAE comes from), templates in overload resolution | [[temp.fct.spec]], [[temp.deduct]], [[temp.over]] |

The rules about concepts are spread over [[temp.constr]], [[temp.concept]], [[expr.prim.req]] and [[over.match.best]]; the topic page [[topics/concepts]] ties them together. For two-phase lookup see the topic page [[topics/two-phase-lookup]].

## Ideas that run through the whole clause

### Templates and specializations

Per [[temp.pre#1]], a template defines a family of classes, functions or variables, an alias for a family of types, or a concept. Specializations can be generated implicitly by instantiation or provided explicitly by the programmer ([[temp.spec]]). Specializations of different templates are always distinct entities ([[temp.pre#6]]). Concepts are the exception: a concept is never instantiated, and a concept-id such as `C<int>` is just a `bool` prvalue ([[temp.concept#5]], [[temp.names#15]]).

### Templates and templated entities

A member function of a class template, a local class inside a function template, and the closure type of a lambda are not templates themselves, but they live inside one. [[temp.pre#8]] calls them **templated entities**. Many rules apply to templated entities in general: for example, only a templated function can have a trailing *requires-clause*, and the discarded branch of `if constexpr` is not instantiated only inside a templated entity.

### Dependent and non-dependent

Every construct in a template definition either depends on template parameters and can only be determined at instantiation time, which is called **dependent**, or can be determined at the definition, which is called non-dependent. Non-dependent parts are looked up and checked at the definition; dependent parts are deferred to instantiation ([[temp.res]]). That is why a dependent qualified name needs `typename` when it is a type, and `template` when it is followed by a template argument list ([[temp.names#11]]).

### Equivalence and functional equivalence

When are two expressions involving template parameters the same? [[temp.over.link]] defines **equivalence** by comparing tokens, not meaning. If two constructs have the same meaning but are written differently (functionally equivalent but not equivalent), and the meaning of the program depends on whether they are the same, the program is IFNDR. This affects redeclarations of function templates and the comparison of atomic constraints ([[temp.constr.atomic]]), and it is also why subsumption between constraints requires using the same named concept ([[temp.constr.order]]).

### So much IFNDR

Templates are compiled in separate translation units and may have several points of instantiation. A compiler cannot compare everything across translation units and points of instantiation, so many rules in this clause make a violation IFNDR (ill-formed, no diagnostic required). Examples: the definition of a function template is not visible where it is implicitly instantiated and there is no explicit instantiation ([[temp.pre#10]]); the same atomic constraint has different satisfaction results at different points in the program ([[temp.constr.atomic]]); a template for which no valid specialization can be generated ([[temp.res]]).

## Changes in C++26

{{c++26}} This clause changed considerably in C++26, and the later pages keep running into it:

- Terminology: what used to be called a non-type template parameter is now a **constant template parameter**, and the corresponding argument a constant template argument. This site uses the new terms throughout.
- A template template parameter is no longer limited to class templates and alias templates; it can also accept concepts and variable templates ([[temp.param]]).
- Fold expanded constraints ([[temp.constr.fold]]) allow subsumption to be determined between constraints such as `(C<Ts> && ...)`.
- Pack indexing `Ts...[N]` ([[temp.names]]).
- Static reflection: a splice specifier can appear before a template argument list ([[temp.names#7]]), and `std::meta::info` can be a constant template argument ([[temp.type]]).
