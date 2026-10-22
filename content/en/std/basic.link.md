---
title: Program and linkage
summary: "What determines a name's linkage (external, module, internal or none); when two declarations declare the same entity and how they must agree; and why a module interface cannot expose entities that belong to one translation unit only."
updated: 2026-10-19
---

!!! tldr
    - A name's linkage decides whether a same-named declaration elsewhere can refer to the same entity: external linkage reaches across translation units, module linkage only within the same module, internal linkage only within this translation unit, and no linkage only within this scope.
    - A `const` variable at namespace scope has internal linkage by default, unless it is `extern`, `inline`, a template, or in a module interface. `const int*` is not a `const` variable.
    - Whether two declarations declare the same entity depends on whether they correspond and have the same target scope; across translation units, the linkage must also be external or module and both must be attached to the same module. Whether name lookup can find the other declaration is irrelevant.
    - All declarations of the same entity must agree in type. Disagreement across translation units requires no diagnostic, and the linker often can't detect it.
    - Declarations visible outside a module interface must not expose TU-local entities, for example by calling a `static` function from an exported inline function. Doing so in ordinary headers is deprecated.

## Is `f` in two translation units the same thing? (¶1–¶2)

¶1 A **program** consists of one or more translation units, which are translated separately and then linked together. A **translation unit** (TU) is roughly a source file together with everything it `#include`s ([[lex.phases]]). Since C++20, a translation unit can also be a module unit, beginning with `export module M;` or `module M;` ([[module.unit]]).

```cpp title="a.cpp"
int counter = 0;              // external linkage
static int hits = 0;          // internal linkage
namespace { int misses = 0; } // internal linkage
void bump() { ++counter; ++hits; ++misses; }
```

```cpp title="b.cpp"
extern int counter;           // the same variable as counter in a.cpp
static int hits = 0;          // unrelated to hits in a.cpp; each has its own
namespace { int misses = 0; } // same as above
void bump();
int main() { bump(); return counter - 1 + hits + misses; }   // returns 0
```

Both files declare `counter`, `hits` and `misses`, with different outcomes. `counter` is one variable, while the other two are two pairs of unrelated variables. What decides this is the name's **linkage**.

¶2 A name has one of four kinds of linkage:

| Linkage | Can a same-named declaration elsewhere refer to the same entity? | Typical examples |
|---|---|---|
| external linkage | yes, from any translation unit, including other modules | ordinary global functions and variables, exported module entities |
| module linkage {{c++20}} | only from translation units of the same module | non-exported namespace-scope entities in a named module |
| internal linkage | only from this translation unit | `static` functions and variables, `const` variables at namespace scope, members of unnamed namespaces |
| no linkage | only from declarations in the same scope | local variables, local classes, function parameters |

Note 1 draws two consequences: all declarations of an entity with internal linkage are in the same translation unit, and all declarations of an entity with module linkage are attached to the same module.

The standard says that names have linkage. When people speak of the linkage of a variable or function, they mean the linkage of the name that declares it. An unnamed type (an unnamed class, a lambda's closure type) has no name and so no linkage, unless it gets a name for linkage purposes through a typedef (see ¶4.3 below).

Linkage and storage duration are different things. `static int n;` in a function has static storage duration but no linkage:

| | Static storage duration | Automatic storage duration |
|---|---|---|
| External linkage | global variables | — |
| Internal linkage | `static` global variables, `const` global variables | — |
| No linkage | `static` variables in functions | ordinary local variables |

## Which names have internal linkage (¶3)

¶3 A name of an entity that belongs to a namespace scope has internal linkage in three cases:

- ¶3.1 a variable, variable template, function or function template explicitly declared `static`;
- ¶3.2 a non-template variable of const-qualified but not volatile type, unless one of the following four holds:
    - ¶3.2.1 it is declared in the purview of a module interface unit (outside the private-module-fragment) or a module partition;
    - ¶3.2.2 it is explicitly declared `extern`;
    - ¶3.2.3 it is `inline`;
    - ¶3.2.4 it was previously declared and the prior declaration did not have internal linkage;
- ¶3.3 a data member of an anonymous union.

```cpp run ok
const int c1 = 1;                 // internal linkage (¶3.2)
extern const int c2 = 2;          // external linkage (¶3.2.2)
inline const int c3 = 3;          // external linkage (¶3.2.3)
const volatile int c4 = 4;        // external linkage: volatile, so ¶3.2 does not apply
constexpr int c5 = 5;             // internal linkage: constexpr implies const
const int* p1 = &c1;              // external linkage: p1 itself is not const
const int* const p2 = &c1;        // internal linkage: p2 itself is const
extern const int z;
const int z = 5;                  // external linkage (¶3.2.4)
static int s = 1;                 // internal linkage (¶3.1)
extern int s;                     // a redeclaration, still internal linkage
int main() { return c1+c2+c3+c4+c5+*p1+*p2+z+s - 23; }
```

Inspecting the executable produced by Clang 23 with `nm`, `c2`, `c4`, `z` and `p1` are global symbols, and `c1` and `s` are local symbols (`c5` and `p2` were optimized away).

The easiest one to misread is `p1`. The `const` in `const int*` qualifies the pointed-to `int`; the type of `p1` itself is not const-qualified, so it has external linkage, and putting it in a header defines it again in every translation unit that includes it.

### Why `const` variables have internal linkage by default

In C, `const int x = 1;` has external linkage. C++ changed it to internal linkage so that `const` constants could replace macros and be written directly in headers:

```cpp title="limits.h"
const int kMaxUsers = 1000;   // every translation unit that includes this has its own separate kMaxUsers
```

If it had external linkage, every translation unit including this header would define the same variable, violating the one-definition rule (ODR, [[basic.def.odr]]). Internal linkage gives each translation unit its own unrelated copy. `kMaxUsers` is usable in constant expressions, and merely reading its value usually takes no storage.

Each exception has its reason:

- `extern` is an explicit request for external linkage; `extern const int x = 1;` is the standard way to define a constant with external linkage.
- An `inline` variable (C++17) is by definition one variable that may be defined in several translation units, and only makes sense with external linkage.
- In the previously-declared case, such as `const int z = 5;` after `extern const int z;`, the latter is the definition of the former, and the linkage of the first declaration carries over.
- A module interface is compiled only once, so the problem of multiple inclusion does not arise. If a `const` variable in it still had internal linkage, it could not be exported, and inline functions in the interface that use it would constitute exposures (see ¶14 below).
- Variable templates are not affected by ¶3.2, because their specializations must be the same entity across translation units. Note 2 adds that a const instantiation of a variable template can have external or module linkage.

## Linkage of other namespace members (¶4)

¶4 An unnamed namespace, and any namespace declared directly or indirectly within an unnamed namespace, has internal linkage; all other namespaces have external linkage.

Variables, functions, classes, enumerations and templates that belong to a namespace scope and are not given internal linkage by ¶3 (¶4.1–¶4.6) get their linkage in this order:

- ¶4.7 if it is a function or function template first declared in a friend declaration and defined there, and the enclosing class is defined within an `export` declaration, it has the same linkage as the enclosing class;
- ¶4.8 otherwise, if it is a function or function template declared in a friend declaration and a corresponding non-friend declaration is reachable, the linkage is determined by that declaration;
- ¶4.9 otherwise, if the enclosing namespace has internal linkage, the name has internal linkage;
- ¶4.10 otherwise, if the declaration is attached to a named module and is not exported, the name has module linkage;
- ¶4.11 otherwise, the name has external linkage.

¶4.9 is how unnamed namespaces work. The unnamed namespace itself has internal linkage, so the variables, functions, classes and templates in it have internal linkage. This is more general than `static`, which cannot be applied to types.

```cpp run ok
namespace { int u = 0; struct Hidden { int z; }; }    // all internal linkage (¶4.9)
namespace outer { namespace { namespace deep { int dv = 0; } } }
// deep is indirectly nested in an unnamed namespace, so dv also has internal linkage
int main() { Hidden h{}; return u + outer::deep::dv + h.z; }
```

¶4.10 is the change brought by modules. Functions, variables and classes in a named module without `export`, which would have had external linkage in a header, now have module linkage: other units of the same module can use them, but code importing the module cannot.

The unnamed classes and enumerations of ¶4.3–¶4.5 rely on a **typedef name for linkage purposes** ([[dcl.typedef]]). C-style `typedef struct { ... } Point;` defines an unnamed class, and the typedef gives it a name that can be identified across translation units, so it can be put in a header like a named class. Since C++20 such unnamed classes must be C-compatible: no member functions, base classes, default member initializers and so on:

```cpp
typedef struct { int a; } P;                 // OK: P is a typedef name for linkage purposes
typedef struct { int b; void f() {} } Q;     // ill-formed: has a member function
enum { red, green } e;                       // an unnamed enumeration uses its first enumerator red as its name for linkage purposes (¶4.5)
```

Clang 23 only gives a `-Wnon-c-typedef-for-linkage` warning for `Q` and compiles the code as usual after the diagnostic, which conforms, since the standard only requires a diagnostic for an ill-formed program.

¶4.7–¶4.8 handle friend functions defined in a class (hidden friends): when the class is exported, such a friend gets external linkage along with the class; when the class is not exported, in a named module it has module linkage.

## Class members and block-scope names (¶5–¶7)

¶5 Member functions, static data members, and named classes and enumerations in class scope (and unnamed classes and enumerations in class scope that get a linkage name through a typedef) have the same linkage as their class. So members of a class with external linkage have external linkage, and members of a class in an unnamed namespace have internal linkage.

¶7 Names not covered by the other rules have no linkage. Unless otherwise noted, a name declared at block scope has no linkage. Local variables, function parameters, local classes (and, by ¶5, members of local classes), typedef names, template parameters and enumerators have no linkage.

An `extern` declaration at block scope is a case otherwise noted. Example 1 in ¶6:

```cpp run ok
static void f();
extern "C" void h();
static int i = 0;               // #1
void q() {
  extern void f();              // internal linkage: redeclares the static f above
  extern void g();              // ::g, external linkage
  extern void h();              // C language linkage
  int i;                        // #2: no linkage, hides #1
  {
    extern void f();            // internal linkage
    extern int i;               // #3: internal linkage, the same variable as #1
  }
}
int main() { }
```

The hard part is #3. Name lookup at #3 can only find #2, the local variable; #1 is hidden. But the **target scope** (the scope the name actually belongs to) of a block-scope `extern` declaration is the enclosing namespace ([[basic.scope.scope#2]]), so #3 and #1 have the same name, the same kind and the same target scope. By ¶8 below, they declare the same entity, and #3 therefore has internal linkage. Whether two declarations declare the same entity depends only on correspondence and target scope, not on the result of name lookup.

Clang 23 follows this rule: assigning to `i` at #3 modifies #1.

!!! history "The old version of this rule"
    Through C++20, the linkage of a block-scope `extern` declaration depended on whether name lookup could see a same-named declaration with linkage; if it could not, the linkage was external. Under the old rule, #3 cannot see the hidden #1, so it got external linkage, which conflicted with the internal linkage of #1, and the program was ill-formed; the standard's example at the time was annotated exactly that way. [[P1787R6]] switched to correspondence and target scope for deciding sameness of entities, and this example changed to internal linkage accordingly.

## When two declarations declare the same entity (¶8–¶10)

¶8 Two declarations declare the **same entity** if:

- they **correspond** ([[g:correspond]]), roughly meaning same name, same kind, and for functions also the same parameter lists and so on ([[basic.scope.scope#4]]);
- they have the same target scope, which is not a function parameter scope or a template parameter scope;
- neither is a name-independent declaration (such as C++26's `_`);

and one of the following three holds:

- ¶8.1 they are in the same translation unit;
- ¶8.2 they both declare type aliases or namespace aliases with the same underlying entity;
- ¶8.3 they both declare names with external or module linkage and are attached to the same module.

For this purpose, a declaration of an unnamed type like `typedef struct {...} P;` is treated as introducing its name for linkage purposes. Note 3 reminds us that there are other cases in which declarations declare the same entity, such as `extern "C"` functions in different namespaces ([[dcl.link]]).

Several conclusions can be read off from this:

- Within one translation unit, declarations that correspond and have the same target scope declare the same entity, regardless of linkage. `static int s; extern int s;` is one `s`.
- Across translation units, the linkage must be external or module and both must be attached to the same module. Names with internal linkage never reach other translation units, which is why the two `hits` in the opening example are unrelated.
- The two `x` in `void f(int x); void f(int x);` are not the same entity, because function parameter scopes are excluded.

### Conflicts between different modules (¶10)

A declaration is **attached** to a module: declarations in the purview of a named module are generally attached to that module, and all others are attached to the global module ([[module.unit]]). By ¶8.3, two declarations attached to different modules are two different entities, even if they are identical.

Note 5 in ¶10 points out that if two declarations correspond but are attached to different modules, and one precedes the other, the program is ill-formed ([[basic.scope.scope#6]]). Example 2, with the verdicts verified with Clang 23:

```cpp title="decls.h"
int f();            // #1, attached to the global module
int g();            // #2, attached to the global module
```

```cpp title="M.cppm (interface of module M)"
module;
#include "decls.h"
export module M;
export using ::f;   // OK: declares no new entity, exports #1
int g();            // error: corresponds to #2 but is attached to M
export int h();     // #3
export int k();     // #4
```

```cpp title="other.cpp"
import M;
static int h();     // error: conflicts with #3
int k();            // error: conflicts with #4
```

The `int g();` line shows the strong ownership of modules. A declaration after `export module M;` is attached to M and is a different entity from `int g();` in the global module, yet the two correspond, so they conflict. To re-export a global-module function from a module, use a using-declaration as with `f`.

So all declarations of an entity are attached to the same module, and the entity is said to be **attached** to that module.

!!! impl "What module linkage looks like at the symbol level"
    Clang uses the strong ownership model: for entities attached to a named module, the module name is encoded in the mangled name:

    ```cpp
    export module M;
    const int k = 1;            // no longer internal by default in a module interface (¶3.2.1): module linkage
    int hidden() { return 2; }  // module linkage
    export int api() { return hidden() + k; }   // external linkage
    ```

    `nm` shows the symbols `__ZW1M1k`, `__ZW1M6hiddenv` and `__ZW1M3apiv`. The exported `api` also carries the `W1M` marker, so same-named entities in two modules do not clash at the linker level either.

### Internal-linkage declarations in header units (¶9)

¶9 If a declaration H that declares a name with internal linkage precedes a declaration D in another translation unit U, and H would declare the same entity as D if it appeared in U, the program is ill-formed. Note 4 explains that such an H can only appear in a **header unit**.

A header unit imported by `import "util.h";` is a separate translation unit, but its declarations precede the importer's code. If the header unit has `static int helper();` and the importer writes `int helper();`, with `#include` this would be a linkage conflict error; with `import`, the two would belong to different translation units and could coexist. ¶9 makes this case ill-formed too, keeping the results of `#include` and `import` consistent.

## Declarations of the same entity must agree (¶11)

¶11 For any two declarations of an entity E:

| ¶ | If one declares E to be | the other must |
|---|---|---|
| 11.1 | a variable or function | declare a variable or function of the same type |
| 11.2 | an enumerator | also be an enumerator |
| 11.3 | a namespace | also be a namespace |
| 11.4 | a type | declare a type of the same kind (`class` and `struct` are interchangeable, `union` and `enum` are not, [[dcl.type.elab]]) |
| 11.5 | a class template | be of the same kind with an equivalent template-head (note 6: default template arguments may differ) |
| 11.6 | a function template, variable template or partial specialization of one | have equivalent template-heads and types |
| 11.7 | an alias template | have an equivalent template-head and aliased type |
| 11.8 | a concept | also be a concept |

Types are compared after all adjustments, with type aliases replaced by the types they denote. Declarations of an array object may differ in the presence or absence of a major array bound, as in `extern int a[]; int a[10];`.

Within one translation unit, violations of this rule are always diagnosed. Example 3:

```cpp error
int f(int x, int x);    // error: the two x are different entities (parameter scopes are excluded by ¶8) and conflict
void g();               // #1
void g(int);            // OK: does not correspond to #1; it is an overload
int g();                // error: corresponds to #1, so it is the same entity, but the type differs
void h();               // #2
namespace h {}          // error: the same entity as #2, but not a function
```

Across translation units it is different. If neither declaration is reachable from the other, no diagnostic is required ({{ifndr}}):

```cpp title="a.cpp"
int config = 42;
```

```cpp title="b.cpp" ifndr
extern double config;            // the same entity, a different type
double read() { return config; } // reads the bytes of an int as a double
```

The linker cannot detect this error. The Itanium C++ ABI (GCC and Clang on Linux and macOS) does not encode the type of a variable in its mangled name, nor the return type of an ordinary function. `void f(int)` and `void f(double)`, which differ in parameter types, get different symbols and the link fails; but `int g();` and `long g();` link successfully and then go wrong at run time. Declaring each entity in exactly one header avoids this class of problem.

¶12 is a note: to link with non-C++ code, use a linkage specification `extern "C"` ([[dcl.link]]). This **language linkage** determines the calling convention and name mangling, and is independent of the linkage discussed on this page.

## A module interface must not expose TU-local entities (¶13–¶19) {{c++20}}

### Where the problem comes from

An inline function in a header that calls a `static` function more or less worked in the days of `#include` only, because each translation unit had its own copy of the `static` function (strictly speaking this already violates the ODR, see [[basic.def.odr]]).

A module interface is compiled only once, and importers see the definitions of the inline functions in the interface. If such a function calls a `static` function in the interface, the importer's translation unit does not have that function at all; it can neither be inlined nor linked.

C++20's solution ([[P1815R2]]) is to define **TU-local entities**, which belong to a single translation unit, and to forbid externally visible declarations in a module interface from exposing them.

### Naming an entity (¶13)

¶13 A declaration D **names** an entity E in the following cases:

- ¶13.1 D contains a lambda-expression whose closure type is E;
- ¶13.2 D contains a reflect-expression `^^E` that represents E, or a splice-specifier that designates E {{c++26}};
- ¶13.3 D is an injected declaration that uses a data member description of type E {{c++26}};
- ¶13.4 E is not a function or function template, and D contains a name (an id-expression, type-specifier, nested-name-specifier, template-name or concept-name) denoting E;
- ¶13.5 E is a function or function template, and D contains an expression that names E ([[basic.def.odr#4]]) or a name that refers to an overload set containing E.

The second half of ¶13.5 means that as soon as an overload with internal linkage appears in an overload set, the declaration names it, even if overload resolution does not end up selecting it. Note 8 adds that in an instantiated declaration, non-dependent names do not refer to overload sets ([[temp.res]]).

### TU-local entities and TU-local values (¶15–¶16)

¶15 The following entities are [[g:tu-local|TU-local]]:

- ¶15.1 a type, type alias, namespace, namespace alias, function, variable or template whose name has internal linkage, and any such entity with no linkage declared within the definition of such an entity (including closure types introduced by lambdas in it);
- ¶15.2 an unnamed type defined outside a class definition, function body and initializer, or one used only to declare TU-local entities, such as the closure type of `static auto x = []{};`;
- ¶15.3 a specialization of a TU-local template;
- ¶15.4 a specialization of a template with a TU-local template argument;
- ¶15.5 a specialization of a template whose (possibly instantiated) declaration is an exposure.

Note 10: a specialization can be produced by implicit or explicit instantiation.

¶16 Values and objects can be TU-local too, because importers use the values of constexpr variables directly (constant folding, template arguments). A value or object is TU-local if:

- ¶16.1 it is of TU-local type;
- ¶16.2 it is, or is a pointer to, a TU-local function or the object associated with a TU-local variable;
- ¶16.3 it is an object of class or array type, any of whose subobjects, or any of the objects or functions referred to by its reference members, is TU-local and usable in constant expressions;
- ¶16.4 it is a reflection value representing a TU-local entity, value or object, or one of several kinds of reflection values related to TU-local types {{c++26}}.

A constexpr function pointer to a `static` function has that function's address as its value, which importers cannot use. ¶16.4 extends the same reasoning to reflection: if `f` is a `static` function, the value of `constexpr auto r = ^^f;` represents a TU-local entity.

### Exposures (¶14)

¶14 A declaration that names a TU-local entity is an **exposure** ([[g:exposure|exposure]]), not counting the following parts:

- ¶14.1 the function body of a non-inline function or function template; but if the function's return type uses a placeholder (`auto`), the deduced return type counts;
- ¶14.2 the initializer of a variable or variable template (the variable's type counts);
- ¶14.3 friend declarations in a class definition;
- ¶14.4 a reference to a non-volatile const object or reference with internal or no linkage initialized with a constant expression, provided it is not an odr-use (it only reads the value, see [[basic.def.odr]]).

In addition, defining a constexpr variable initialized to a TU-local value is an exposure.

These exceptions correspond exactly to what importers do or do not need to see:

- The body of a non-inline function is compiled only in its own translation unit; importers need only the declaration, so the body can freely use TU-local entities.
- The body of an inline function is used by importers (inlining, ODR merging) and cannot be ignored.
- For a function returning `auto`, importers need to know the deduced type.
- A constant whose value is merely read is substituted directly; importers do not need the entity itself.

Note 9: an inline function template can be an exposure even though certain explicit specializations of it would be usable in other translation units.

### Consequences of violations (¶17–¶18)

¶17 If a declaration of a non-TU-local entity (including an instantiated declaration), or a deduction guide, in a module interface unit (outside the private-module-fragment) or a module partition is an exposure, the program is ill-formed. Such a declaration in any other context is deprecated ([[depr.local]]).

The second sentence means that in ordinary headers, an inline function calling a `static` function is still valid, just deprecated.

¶18 If a declaration in one translation unit names a TU-local entity declared in another translation unit that is not a header unit, the program is ill-formed. A declaration instantiated for a template specialization is considered to appear at the point of instantiation of that specialization ([[temp.point]]).

¶17 governs what interfaces may not expose, and ¶18 governs what importers may not use. Template instantiation produces declarations in the importer's translation unit from definitions in the interface, so both rules together are needed to cover it.

### Example (¶19)

Below is the main part of Example 4 in the standard (with the reflection-related lines omitted), annotated line by line. Translation unit #1 is the interface of module A:

```cpp title="TU #1: export module A;"
export module A;
static void f() {}
inline void it() { f(); }           // error: the inline function body counts and names the TU-local f
static inline void its() { f(); }   // OK: its itself is TU-local
template<int> void g() { its(); }   // OK: the body of a non-inline function template does not count (¶14.1)
template void g<0>();               // explicit instantiation of g<0>

decltype(f) *fp;                    // error: the variable's type counts, and decltype(f) names f
auto &fr = f;                       // OK: the initializer does not count (¶14.2)
constexpr auto &fr2 = fr;           // error: the constexpr variable's value refers to f, a TU-local value
constexpr static auto fp2 = fr;     // OK: fp2 has internal linkage and is TU-local itself

struct S { void (&ref)(); } s{f};               // OK: s is not constexpr
constexpr extern struct W { S &s; } wrap{s};    // OK: s is not usable in constant expressions, so ¶16.3 does not apply

static auto x = []{f();};           // OK: x and its closure type are both TU-local
auto x2 = x;                        // error: x2's type is the TU-local closure type
int y = ([]{f();}(),0);             // error: this closure type is not TU-local,
                                    //   and its inline operator() names f
int y2 = (x,0);                     // OK: the initializer does not count

namespace N {
  struct A {};
  void adl(A);
  static void adl(int);
}
void adl(double);

inline void h(auto x) { adl(x); }   // OK, but certain specializations are exposures
```

Translation unit #2 is an implementation unit of module A:

```cpp title="TU #2: module A;"
module A;
void other() {
  g<0>();                           // OK: g<0> was explicitly instantiated in TU #1
  g<1>();                           // error: g<1> is instantiated here and uses its, a TU-local entity of TU #1 (¶18)
  h(N::A{});                        // error: in the instantiation, the overload set ADL gives adl(x) contains the TU-local N::adl(int)
  h(0);                             // OK: the argument is int, ADL does not look in N, and only ::adl(double) is found
  adl(N::A{});                      // OK: lookup here does not find N::adl(int) from the other TU
  fr();                             // OK: calls f through the non-TU-local reference fr
  constexpr auto ptr = fr;          // error: fr is not usable in constant expressions here
}
```

A few contrasts are worth noting:

- `it` and `its` call the same function. `it` is an inline function with module linkage, whose body importers need, so it is an exposure; `its` is `static inline`, TU-local itself, and promises nothing to the outside.
- Using `f` indirectly through `fr` is allowed: calling through a reference at run time does not need to know `f`'s name. But other translation units cannot use `fr` in constant evaluation, because its initializer is a TU-local value ([[expr.const]]).
- The closure type in the initializer of `y` is not used only to declare TU-local entities, so it is not TU-local; its `operator()` is inline and calls `f`, which is an exposure. `y2` only uses the existing `x`, and the initializer does not count.

The omitted lines of the standard's example illustrate ¶16.4: `constexpr std::meta::info r3 = ^^f;` is an exposure, because the value of `r3` represents the TU-local entity `f`.

!!! impl "Clang's implementation status"
    Compiling TU #1 above, Clang 23 gives `-WTU-local-entity-exposure` warnings only for `it` and `auto x2 = x;`, with no diagnostic for `decltype(f) *fp;`, `fr2` or `y`. The standard makes all of these ill-formed, so at the time of writing Clang's implementation is incomplete.

## Implementation view

!!! impl "What linkage looks like in object files"
    Observed with `nm` on Clang 23 (Mach-O):

    | Declaration | Symbol | Notes |
    |---|---|---|
    | an ordinary global function `int use();` | `T __Z3usev` | an uppercase letter means a global symbol (external linkage) |
    | `static int s1 = 1;` | `d __ZL2s1` | a lowercase letter means a local symbol; `L` is the Itanium ABI marker for internal linkage |
    | `hidden()` in an unnamed namespace | `t __ZN12_GLOBAL__N_16hiddenEv` | `_GLOBAL__N_1` is the mangling of the unnamed namespace |
    | `extern const int z; const int z = 5;` | `S _z` | external linkage; the variable name is not mangled |
    | non-exported `hidden()` in module M | `T __ZW1M6hiddenv` | module linkage: a global symbol with the module name in the mangled name |

    A namespace-scope variable whose type is a class in an unnamed namespace (such as `Hidden h;`) has external linkage per ¶4, but Clang emits it as a local symbol. Other translation units cannot spell its type and so cannot validly declare it, so this optimization is unobservable.

## History

!!! history
    - C++98 had three kinds: external, internal and no linkage. Declaring objects `static` at namespace scope was deprecated in favor of unnamed namespaces; at the time, members of unnamed namespaces had external linkage, just with a unique name that other translation units could not spell.
    - C++11 undeprecated `static`, gave unnamed namespaces and their members internal linkage, and allowed local and unnamed types as template arguments.
    - C++17 introduced inline variables; an `inline const` variable has external linkage (¶3.2.3).
    - C++20 modules ([[P1103R3]]) brought module linkage and attachment, and `const` variables in module interfaces no longer default to internal linkage; [[P1815R2]] introduced TU-local entities and exposures; typedef names for linkage purposes are limited to C-compatible unnamed classes.
    - [[P1787R6]] rewrote the same-entity test (¶8) in terms of correspondence and target scope, which changed the verdict for the block-scope `extern` example.
    - C++26 added reflection-related naming rules (¶13.2–¶13.3) and TU-local reflection values (¶16.4), and excluded name-independent declarations from declaring the same entity.

## Common misconceptions

!!! pitfall "`const int*` is a const variable"
    `const int* p = ...;` at namespace scope has external linkage, and putting it in a header causes duplicate definitions. For internal linkage write `const int* const p`; for one instance in the whole program write `inline const int* p`.

!!! pitfall "A `static` variable in a function has internal linkage"
    It has no linkage. Static storage duration has nothing to do with internal linkage. That a `static` local variable in an inline function exists only once in the whole program is guaranteed by the ODR ([[basic.def.odr]]), not an effect of linkage.

!!! pitfall "The linker catches type mismatches across translation units"
    `int x;` and `extern long x;` in another translation unit are the same entity with different types. This is IFNDR (ill-formed, no diagnostic required), and the linker usually reports nothing.

!!! pitfall "Inline functions in headers can safely call `static` functions"
    In non-module code this is deprecated (¶17), and the inline function in each translation unit calls a different `static` function, which strictly speaking violates the ODR. Make the helper inline too, or put it in a `detail` namespace and declare it inline.

## Questions

!!! question "Question 1"
    What linkage does each of these names have?

    ```cpp
    namespace { namespace X { int a; } }
    struct S { static int b; };
    const int c = 1;
    constexpr const char* d = "hi";
    void f() { static int e; struct L { void m(); }; }
    template<class T> const T g = T();
    ```

<details markdown="1">
<summary>Answer</summary>

- `X` and `X::a`: internal linkage. `X` is nested in an unnamed namespace (¶4), and `a` gets internal linkage by ¶4.9.
- `S` and `S::b`: external linkage (¶4.3, ¶5).
- `c`: internal linkage (¶3.2).
- `d`: `constexpr` makes the pointer itself const, so its type is `const char* const`; ¶3.2 applies, giving internal linkage.
- `e`: no linkage; it is at block scope (¶7).
- `L` and `L::m`: no linkage. `L` is a local class (¶7), and its members follow the class (¶5).
- `g`: ¶3.2 applies only to non-template variables, so by ¶4.6 and ¶4.11 it has external linkage.
</details>

!!! question "Question 2"
    In `static int s; void f() { int s; { extern int s; } }`, does the innermost `extern int s;` declare a new `s` with external linkage, or does it refer to the global `s`? What about under the C++20 rules?

<details markdown="1">
<summary>Answer</summary>

Under the current rules, it refers to the global `s`. The target scope of a block-scope `extern` declaration is the enclosing namespace ([[basic.scope.scope#2]]); it corresponds to `static int s;`, has the same target scope, and is in the same translation unit, so ¶8.1 makes them the same entity, and it has internal linkage. The local `int s;` in between hides the global `s` only for name lookup and does not affect this. This is #3 in Example 1.

Under the rules of C++20 and earlier, linkage depended on whether lookup could see a declaration with linkage. The hidden global `s` is not visible, so the innermost `s` got external linkage, which conflicted with the internal linkage of the global `s`, and the program was ill-formed.
</details>
