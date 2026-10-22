---
title: "Preamble: names, entities and variables"
summary: "The basic vocabulary of Chapter 6: what counts as a name, which declarations introduce names, which things are entities, and what variables and local entities are."
updated: 2026-10-19
---

!!! tldr
    - There are only four kinds of name: identifiers, conversion-function-ids like `operator int`, operator-function-ids like `operator+`, and literal-operator-ids like `operator""_km`. Labels, module names and identifiers in attributes are not names and take no part in name lookup.
    - Every name is introduced by a declaration; a name denotes an entity, and it sees through aliases: after `using I = int;`, the name `I` denotes `int`.
    - A variable is an object or reference introduced by a declaration. Non-static data members and non-type template parameters are not variables, so the ODR's rules about variables don't govern them.
    - Local entities are variables with automatic storage duration, the corresponding structured bindings, result bindings, and `*this`. Only they need to be captured when used in a lambda; `static` local variables don't.

## What counts as a name (¶3)

```cpp run ok
int f() {
  int x = 0;
x:                      // the label x is not a name and doesn't conflict with the variable x
  if (++x < 3) goto x;  // the x after goto is not a name either
  return x;
}
int main() { return f() - 3; }
```

The same function has a variable `x` and a label `x`, yet they don't conflict. The reason is that the identifier of a label is not a **name** at all, so rules such as name lookup and scope conflicts don't apply to it.

¶3 specifies that a name has only four forms:

| Form | Examples |
|---|---|
| *identifier* token | `x`, `std`, `vector` |
| *conversion-function-id* | `operator int`, `operator bool` |
| *operator-function-id* | `operator+`, `operator()`, `operator new` |
| *literal-operator-id* | `operator""_km` |

¶3.1 also excludes three kinds of identifier: the identifier of a label and the suffix in a *literal-operator-id* (`_km` on its own is not a name; the whole `operator""_km` is); the identifier after `goto`; and identifiers in a module name (`my`, `lib` in `export module my.lib;`) or an attribute token (`gnu`, `always_inline` in `[[gnu::always_inline]]`).

Each of these three has its own matching mechanism: labels are matched within a function by the label rules ([[stmt.label]]), module names are resolved by the module system ([[module.unit]]), and attribute tokens are recognized by the implementation ([[dcl.attr.grammar]]). Excluding them from names keeps the rules for name lookup and linkage from catching them by accident.

Keywords are not identifier tokens ([[lex.key]]), so they are not names either. Macro names are replaced during preprocessing ([[cpp.replace]]), so the compiler no longer sees them during semantic analysis. Macros are not subject to the ODR, which is one reason a header compiled with different `-D` options in different translation units can silently violate the ODR (see [[basic.def.odr]]).

### When two names are the same (¶4)

¶4 specifies the conditions for two names to be the same separately for each form: identifiers need the same character sequence; conversion-function-ids need equivalent target types ([[temp.over.link]]), not the same spelling; operator-function-ids need the same operator; literal-operator-ids need the same suffix.

```cpp run ok
struct S { operator int() const { return 1; } };
using I = int;
int g(S s) {
  return s.operator I() + s.operator int();  // the same name, the same function
}
int main() { return g({}) - 2; }
```

When [[basic.scope.scope]] decides whether two declarations correspond (and so are a redeclaration, an overload, or a conflict), the first step is checking whether their names are the same.

## Every name is introduced by a declaration (¶5)

¶5 specifies that every name is introduced by a **declaration**. Declaration here is a semantic notion, broader than the grammar non-terminal *declaration* (Note 3): function parameters, the identifiers in a structured binding, and a lambda's init-capture all count.

| ¶ | Form of declaration | Example |
|---|---|---|
| 5.1 | *name-declaration*, *block-declaration*, *member-declaration* | `namespace N {}`, `using T = int;` |
| 5.2 | *init-declarator* | `a = 1` and `*p` in `int a = 1, *p;` |
| 5.3 | identifier in a structured binding | `x`, `y` in `auto [x, y] = p;` |
| 5.4 | identifier in a *result-name-introducer* in a postcondition {{c++26}} | `r` in `post(r: r > 0)` |
| 5.5 | *init-capture* | `n` in `[n = 42]{}` |
| 5.6 | *condition* with a declarator | `if (int x = f())` |
| 5.7 | *member-declarator* | `m : 3` in `struct S { int m : 3; };` |
| 5.8 | *using-declarator* | `using std::swap;` |
| 5.9 | *parameter-declaration* | function parameters, non-type template parameters |
| 5.10–5.13 | type template parameters and the three kinds of template template parameter | `class T`, `template<class> class TT`, and C++26's variable template parameters and concept template parameters |
| 5.14 | an *elaborated-type-specifier* that introduces a name | `struct Fwd` in `struct Fwd*` |
| 5.15 | *class-specifier* | `struct S { };` |
| 5.16 | *enum-specifier*, *enumerator-definition* | `enum E { a };` |
| 5.17 | *exception-declaration* | `catch (std::exception& e)` |
| 5.18 | implicit declaration of an injected-class-name | `S` inside class `S` |

A range-based `for`'s *for-range-declaration* is rewritten into one or more of the above (Note 4, [[stmt.ranged]]). [[basic.scope.pdecl]] gives the point of declaration for each of these forms.

Conversely, not every declaration introduces a name. `static_assert(true);`, the empty declaration `;`, `using namespace std;`, and the explicit instantiation `template class X<int>;` are all declarations, but introduce no name ([[basic.def#1]]).

!!! note "Names may denote types or templates (¶6)"
    ¶6 is a note: when parsing a program, a name usually has to be looked up before we know whether it is a type or a template. This is why the C++ grammar is context-dependent: whether `T * p;` is a multiplication or a pointer declaration depends on whether `T` is a type; whether `a < b > c;` is a comparison or a declaration depends on whether `a` is a template. Inside a template this question can't be answered until instantiation, so `typename` and `template` are needed for disambiguation ([[temp.res]]).

## Entities and denoting (¶8)

A name is a token in the source; the thing it refers to is an **entity**. ¶8 lists all fifteen kinds of entity:

> variable, structured binding, result binding, function, enumerator, type, type alias, non-static data member, bit-field, template, namespace, namespace alias, template parameter, function parameter, *init-capture*.

Objects and values are not among them. A variable is an entity; the object the variable declares is not. The object created by `new int` has no name and is not an entity. Expressions, statements, labels, macros and modules are not entities either. C++26's reflection values (`std::meta::info`) can represent entities as well as non-entities such as values, objects and data member descriptions ([[basic.fundamental]]), so the related rules have to treat these separately.

Every entity has an **underlying entity**. Unless otherwise specified, the underlying entity is the entity itself; type aliases and namespace aliases are the exceptions, whose underlying entities are the type or namespace they stand for (Note 6).

A name **denotes** the underlying entity of the entity declared by the declaration that introduces it. In other words, names see through aliases:

```cpp run ok
namespace very_long_name { int v = 1; }
namespace V = very_long_name;  // namespace alias; underlying entity is very_long_name
using I = int;                 // type alias; underlying entity is int

int main() {
  I i = V::v;  // V denotes very_long_name, I denotes int
  return i - 1;
}
```

An alias is itself an entity, so it can be declared, has its own scope, and is a distinct value under reflection. A name denotes the underlying entity, so aliases are semantically transparent: `I` and `int` are the same type. [[basic.scope.scope#6]] allowing `namespace B = A;` to be repeated, and [[basic.link#8]] deciding whether two alias declarations declare the same entity, both depend on this distinction.

A name can be introduced by multiple declarations; for example, the overloads `f(int)` and `f(double)` both introduce the name `f`. Name lookup then yields a set of declarations ([[basic.lookup]]), from which overload resolution selects a function.

## Variables (¶7)

¶7 specifies that if a declaration D declares an object, or declares a reference (other than a non-static data member), and D is not the *parameter-declaration* of a template parameter, then D introduces a **variable**.

| Declaration | A variable? | Why |
|---|---|---|
| `int x;` (any scope) | Yes | Declares an object |
| `static int s;` (in a class) | Yes | A static data member is an object |
| `int m;` (in a class) | No | A non-static data member is a different kind of entity |
| `int& r;` (in a class) | No | A reference, but a non-static data member |
| `int& r = x;` (in a block) | Yes | A reference can be a variable too |
| `p` in `void f(int p)` | Yes | A function parameter declares an object |
| `N` in `template<int N>` | No | The *parameter-declaration* of a template parameter is excluded |
| `a` in `auto [a, b] = t;` | No | A structured binding is a different kind of entity; the declaration separately introduces an unnamed variable |
| `n` in `[n = 1]{}` | No | An init-capture is a different kind of entity |

A non-static data member is not a variable because it doesn't correspond to a separately existing piece of storage: each class object has its own copy, and the member itself only describes a type and an offset. The ODR's rules about variables, storage duration, and linkage are all meaningless for it. A static data member is a single object for the whole program, so it is a variable.

A non-type template parameter `N` is just a value in an instantiation; a scalar `N` is a prvalue whose address can't be taken, so it isn't a variable either.

## Local entities (¶9)

```cpp run error
int g = 1;
void f(int n) {
  static int s = 2;
  auto l = [] { return g + s; };  // OK: g and s are not local entities
  auto bad = [] { return n; };    // error: n is a local entity and is not captured
  (void)l; (void)bad;
}
int main() { f(0); }
```

¶9 specifies four kinds of **local entity**: variables with automatic storage duration ([[basic.stc.auto]], i.e. variables in a block declared without `static`, `thread_local` or `extern`, plus function parameters); structured bindings whose corresponding variable is such a variable; result bindings in postconditions ([[dcl.contract.res]]) {{c++26}}; and `*this` ([[expr.prim.this]]).

A local entity's storage belongs to one particular function call. A lambda's body or a local class's member function may run during another call, or even after the enclosing function has returned, when there is no definite `n` to access. So [[basic.def.odr#10]] specifies that a local entity can be used directly only within a certain region, and crossing a lambda requires a capture. A variable with static storage duration exists once for the whole program and can be used directly anywhere.

`*this` is listed as a local entity, so accessing members inside a lambda requires capturing `this`, under the same rules as ordinary local variables.

## The same name across translation units (¶10)

¶10 When the same name appears in several translation units (separately compiled source files together with the headers they include), whether it denotes the same entity depends on its **linkage**. The detailed rules are in [[basic.link]]: names with external linkage or module linkage can denote the same entity across translation units, while a name with internal linkage is a separate entity in each translation unit.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1–¶2 are two notes explaining that Chapter 6 presents the basic concepts of the language (objects and names, value categories, declarations and definitions, types, scope, linkage, storage duration, program start and termination, fundamental and compound types), and that concepts affecting only one part of the language are discussed in the corresponding Clauses.

</details>

## History

!!! history
    - Up to C++20, the list of entities also included values and objects, and a name was defined as the use of an identifier etc. that denotes an entity or a label, so labels fell within the discussion of names.
    - C++23's [[P1787R6]] (Declarations and where to find them) rewrote the model of scope and name lookup, replacing the old description of declarative regions with the list of declarations that introduce names (today's ¶5) (see [[basic.scope]]).
    - The current draft's list of entities drops values and objects, adds type aliases, namespace aliases, function parameters, template parameters and so on, and handles aliases through underlying entities. C++26 contracts brought result bindings, and static reflection lets a *splice-expression* designate entities too.

## Common misconceptions

!!! pitfall "Objects are variables"
    The object created by `new int` has no name and is not a variable. Discussions of lifetime ([[basic.life]]) are about objects; discussions of linkage, the ODR and scope are about variables and names.

!!! pitfall "Non-static data members can be odr-used too"
    odr-use is a kind of use defined in [[basic.def.odr]] that decides whether a variable or function must have a definition. The `m` in `struct S { int m; };` is not a variable, so the odr-use rules for variables don't apply to it. This is related to being able to write `sizeof(S::m)` without an object ([[expr.prim.id]]).

## Questions

!!! question "Question 1"
    Which variables does the following introduce? Which entities are not variables?

    ```cpp
    struct P { int a; static int b; int& c; };
    template<int N, class T> void f(T t, int (&arr)[N]) {
      auto [x, y] = std::pair{1, 2};
      auto l = [z = t] { return z; };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

The variables are `P::b` (a static data member), `t` and `arr` (function parameters, declaring an object and a reference respectively), `l`, and the unnamed variable introduced by the structured binding declaration ([[dcl.struct.bind]]).

The entities that are not variables are `P::a` and `P::c` (non-static data members; `c` is a reference but is still excluded by ¶7.1); `N` and `T` (template parameters); `x` and `y` (structured bindings); `z` (an init-capture); plus the class `P` and the function template `f`.
</details>

!!! question "Question 2"
    Is a `static` local variable a local entity? Why can a lambda use it without capturing it?

<details markdown="1">
<summary>Answer</summary>

No. ¶9 lists only variables with automatic storage duration as local entities, and a `static` local variable has static storage duration. The odr-usable restriction in [[basic.def.odr#10]] applies only to local entities, so lambdas and member functions of local classes can use it directly.
</details>

## Summary

| Concept | In one sentence |
|---|---|
| [[g:name|Name]] | An identifier (except labels, goto targets, module names and attribute tokens), `operator T`, `operator@`, `operator""_x` |
| Declaration | One of the 18 forms in ¶5; not the same as the grammar non-terminal *declaration* |
| [[g:entity|Entity]] | 15 kinds, not including objects and values |
| Denote | A name denotes the underlying entity, seeing through aliases |
| [[g:variable|Variable]] | An object or reference introduced by a declaration, excluding non-static data members and template parameters |
| [[g:local-entity|Local entity]] | Automatic variables, the corresponding structured bindings, result bindings, `*this` |
