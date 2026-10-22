---
title: Type specifiers
summary: "The keywords and names in a declaration that determine its type: which ones can be combined, the semantics of const and volatile, the types denoted by simple type specifiers, elaborated forms such as struct X, and C++26 pack indexing and type splicing."
updated: 2026-10-19
---

!!! tldr
    - A declaration can generally have only one type specifier. `unsigned long long int` works because the standard lists six combination exceptions, and the keywords can appear in any order.
    - C++ has no implicit int: except for constructors, destructors and conversion functions, a declaration must have a type specifier other than `const`/`volatile`.
    - An object can't be modified through a const access path; if the object itself is const, casting away const with `const_cast` and modifying it is undefined behavior.
    - `char`, `signed char` and `unsigned char` are three distinct types; `signed` only matters for `char`.
    - An elaborated type specifier such as `struct X` can forward-declare and can get around name hiding, but it can't refer to a typedef name, and its keyword must match the kind of class.

## Which keywords can be combined [dcl.type.general]

<div class="compare" markdown="1">

```cpp run ok
#include <type_traits>
// any order: unsigned long long
int long unsigned long x = 0;
static_assert(std::is_same_v<
    decltype(x), unsigned long long>);
int main() {}
```

```cpp error
long long long a;  // error
signed unsigned b; // error
unsigned double c; // error
int main() {}
```

</div>

On the left, four keywords make up one type; on the right, every line is ill-formed. What separates them is one rule in this subclause and six exceptions.

¶1 A **type-specifier** is the part of a declaration's specifiers that describes the type. There are four kinds: simple type specifiers (`int`, class names, `decltype(…)`, etc., see the next section), elaborated type specifiers (`struct X`), `typename` specifiers (`typename T::type`), and cv-qualifiers (`const`, `volatile`). Adding class definitions `struct X { … }` and enumeration definitions `enum E { … }` gives the **defining-type-specifier**.

The two levels are distinguished because some positions don't allow defining new types. Types in `sizeof(T)`, `static_cast<T>` and template arguments can only be made of type specifiers, so `sizeof(struct { int x; })` is ill-formed; ordinary declarations and alias declarations can define types. Attributes at the end of a specifier sequence appertain to the type determined by the preceding specifiers and only take effect in that one declaration.

### At most one, with six exceptions (¶2)

¶2 The general rule: the complete specifier sequence of a declaration has at most one defining type specifier. There are only six exceptions:

| ¶ | Exception | Example |
|---|---|---|
| 2.1 | `const` can be combined with any type specifier except itself | `const int`, `const T` |
| 2.2 | `volatile` can be combined with any type specifier except itself | `volatile const int` |
| 2.3 | `signed` or `unsigned` can be combined with `char`, `long`, `short` or `int` | `unsigned char` |
| 2.4 | `short` or `long` can be combined with `int` | `short int` |
| 2.5 | `long` can be combined with `double` | `long double` |
| 2.6 | `long` can be combined with `long` | `long long` |

All of C's multi-keyword type names rely on these six. `long long long` is invalid because ¶2.6 only lets one `long` combine with another `long`, and no rule lets a third `long` combine with `long long`. Likewise, `long double long` is invalid.

```cpp error
long float f;       // error: long only combines with int, double and long
short long s;       // error
signed bool b;      // error
unsigned char8_t c; // error: char8_t, char16_t, char32_t and wchar_t can't take a sign specifier
typedef int T;
T unsigned u;       // error: a type name can't combine with unsigned
```

[[dcl.type.simple#4]] adds that these combinable keywords can be intermixed with other specifiers in any order: `long static unsigned const long x = 0;` is equivalent to `static const unsigned long long x = 0;`.

Writing `const const int` directly violates ¶2.1; Clang 23 only gives a `-Wduplicate-decl-specifier` warning, which satisfies the requirement to diagnose. Duplicate const arising through a typedef or template parameter is a different matter; see the section on cv-qualifiers below.

### No implicit int (¶3)

¶3 Except in declarations of constructors, destructors and conversion functions, the complete specifier sequence must contain at least one defining type specifier that is not a cv-qualifier. C89 allowed omitting the type, defaulting to `int`; C++ doesn't:

```cpp error
const x = 1;     // error: const int in C89
static y;        // error
f() { }          // error: functions must have a return type too
```

## Simple type specifiers [dcl.type.simple]

### Keywords and the types they denote (Table 17)

¶1 **Simple type specifiers** (simple-type-specifier) include the keywords for fundamental types (`char`, `int`, `long`, `unsigned`, `double`, `void`, etc.), type names (class names, enumeration names, typedef names, possibly qualified), template specializations such as `std::vector<int>`, class template names without an argument list (CTAD), the placeholder types `auto` and `decltype(auto)`, and three **computed type specifiers** (computed-type-specifier): `decltype(e)`, pack indexing `Ts...[I]`, and type splicing `[: r :]`. `decltype`, `auto` and CTAD each have their own page: [[dcl.type.decltype]], [[dcl.spec.auto]], [[dcl.type.class.deduct]].

¶3 Table 17 lists all valid combinations of fundamental type keywords. Arranged by resulting type below; spellings on the same row are equivalent, and keyword order is free:

| Type | Spellings |
|---|---|
| `char`, `signed char`, `unsigned char` | Each has only this one spelling; they are three distinct types |
| `char8_t`, `char16_t`, `char32_t`, `wchar_t`, `bool` | Each its own single keyword |
| `int` | `int`, `signed`, `signed int` |
| `unsigned int` | `unsigned`, `unsigned int` |
| `short int` | `short`, `short int`, `signed short`, `signed short int` |
| `unsigned short int` | `unsigned short`, `unsigned short int` |
| `long int` | `long`, `long int`, `signed long`, `signed long int` |
| `unsigned long int` | `unsigned long`, `unsigned long int` |
| `long long int` | `long long`, `long long int`, `signed long long`, `signed long long int` |
| `unsigned long long int` | `unsigned long long`, `unsigned long long int` |
| `float`, `double`, `long double`, `void` | Each unique |

¶4 Note 2 points out that `signed` only has an effect on `char`. Whether `char` is signed is implementation-defined {{impl}}, and `signed char` forces it to be signed; moreover `char`, `signed char` and `unsigned char` are three distinct types ([[basic.fundamental]]). `signed int` and `int`, however, are the same type.

```cpp run ok
#include <type_traits>
static_assert(std::is_same_v<signed int, int>);
static_assert(!std::is_same_v<char, signed char>);
static_assert(!std::is_same_v<char, unsigned char>);
int main() {}
```

### Placeholders for deduced class types (¶3)

The first half of ¶3 says that a type specifier of one of the following three forms is a **placeholder for a deduced class type**, used for class template argument deduction (CTAD, [[dcl.type.class.deduct]]):

- ¶3.1 a template name without a template argument list, possibly qualified, such as `std::pair` in `std::pair p(1, 2.0);`;
- ¶3.2 a `pack-index-template-name`, i.e. a template name taken from a template template parameter pack by pack indexing;
- ¶3.3 {{c++26}} a splice `[: r :]` designating a class template or alias template.

The qualifying part must be non-dependent, and the template must be a **deducible template**:

- ¶3.4 a class template;
- ¶3.5 a type template template parameter;
- ¶3.6 an alias template A whose defining type is of the form `nested-name-specifier(opt) template(opt) simple-template-id`, where the qualifying part is non-dependent and the template name of the `simple-template-id` in turn names a deducible template (which can't be a template template parameter of A itself).

¶3.6 is C++20 alias template CTAD. `template<class T> using Vec = std::vector<T>;` is a deducible template; `template<class T> using Ptr = T*;` isn't, because `T*` is not a template specialization.

```cpp run ok
#include <vector>
#include <utility>
template<class T> using Vec = std::vector<T>;
int main() {
    std::pair p(1, 2.0);   // std::pair<int, double>
    Vec v{1, 2, 3};        // C++20: std::vector<int>
    return int(v.size()) - 3 + (p.first - 1);
}
```

Note 1 points out that where CTAD would happen, the **injected-class-name** (the implicit declaration of a class template's own name inside it, [[temp.local]]) is not treated as a template name. So writing `A x(…);` inside class template `A` means the current specialization `A<T>` and doesn't trigger deduction.

## const and volatile [dcl.type.cv]

For how const-qualified types themselves are defined, see [[basic.type.qualifier]]. This subclause covers the rules for cv-qualifiers as specifiers and the consequences of modifying const objects and accessing volatile objects.

### Rules for writing them (¶1–¶2)

¶1 In a cv-qualifier sequence, `const` and `volatile` may each appear at most once. If the specifier sequence contains a cv-qualifier, a declarator must follow, so `const struct S { };` is ill-formed: there's nothing for the const to qualify.

Redundant cv-qualification introduced through a typedef or template parameter is ignored:

```cpp run ok
#include <type_traits>
typedef const int CI;
const CI x = 1;        // const const int, i.e. const int
static_assert(std::is_same_v<decltype(x), const int>);
template<class T> using AddConst = const T;
static_assert(std::is_same_v<AddConst<const int>, const int>);
int main() {}
```

¶2 is a note: declaring a variable const affects its linkage (non-volatile const variables at namespace scope have internal linkage by default, [[basic.link#3]]) and whether it can be used in constant expressions ([[expr.const.init]]). The definition of a const object must have an initializer, or its type must be default-initializable to a determinate value ([[dcl.init.general]]).

### Access path versus the object itself (¶3–¶4)

```cpp run ub
int main() {
    int i = 2;
    const int* cip = &i;   // const access path to a non-const object
    // *cip = 4;           // error: can't modify through a const access path
    int* ip = const_cast<int*>(cip);
    *ip = 4;               // OK: i itself is not a const object

    const int* ciq = new const int(3);
    int* iq = const_cast<int*>(ciq);
    *iq = 4;               // UB: modifies a const object
    delete ciq;
}
```

¶3 A pointer or reference to a cv-qualified type need not actually point or refer to a cv-qualified object, but it is treated as if it does: even if the object itself could be modified, it can't be modified through a const access path. Note 4 points out that this restriction can't be circumvented without a cast.

¶4 Any attempt to modify a const object during its lifetime is undefined behavior {{ub}}.

!!! std
    Any attempt to modify a const object during its lifetime results in undefined behavior.

So there are two questions to ask separately. Whether the expression's type has const determines whether `*p = 4` compiles; whether the object itself is const determines whether modifying it at run time is UB. `const_cast` only changes the former.

A **const object** is defined in [[basic.type.qualifier]]: an object of type `const T`, or a non-mutable subobject of such an object. A mutable member is not a const object:

```cpp run ub
struct X { mutable int i; int j; };
struct Y { X x; Y() { } };
const Y y;            // has a user-provided constructor, so the initializer can be omitted

int main() {
    y.x.i++;          // OK: mutable member
    Y* p = const_cast<Y*>(&y);
    p->x.i = 99;      // OK
    p->x.j = 99;      // UB: y.x.j is a subobject of a const object
}
```

Making modification of a const object UB gives implementations two freedoms: putting const objects in read-only storage, and assuming their value never changes and replacing reads with the initial value.

```cpp run ub
#include <cstdio>
const int limit = 10;
int main() {
    int* p = const_cast<int*>(&limit);
    *p = 20;                        // UB
    std::printf("%d\n", limit);
}
```

In our tests (Apple Silicon, Clang 23), at `-O0` the program crashes with a Bus error at the write, because `limit` is in a read-only segment; at `-O2` it prints `10` and exits normally: the read was replaced by the constant and the write was deleted. Adding `-fsanitize=address,undefined` doesn't produce a diagnostic for writing a const object either: UBSan doesn't check such writes, and ASan only reports the BUS signal that follows.

!!! note "During construction and destruction"
    ¶4 only covers modification during the lifetime. A const object is not yet, or no longer, const while its constructor or destructor runs ([[class.ctor.general]], [[class.dtor]]), so a constructor can assign to members.

### volatile (¶5–¶6)

¶5 The semantics of an access to an object through a volatile glvalue (an expression that designates an object, see [[basic.lval]]) are implementation-defined {{impl}}. If an object is defined with a volatile type and accessed through a non-volatile glvalue, the behavior is undefined {{ub}}:

```cpp ub
volatile int reg = 0;
int read_wrong() {
    return *const_cast<int*>(&reg);   // UB: volatile cast away
}
```

¶6 is a note: volatile is a hint to the implementation to avoid aggressive optimization, because the object's value might be changed by means undetectable by the implementation; on some implementations, accessing it requires special hardware instructions. Its intended semantics in C++ are the same as in C.

Volatile accesses are part of observable behavior ([[intro.abstract]]) and can't be merged, deleted or reordered relative to each other; memory-mapped hardware registers depend on this. It provides no atomicity and establishes no ordering between threads. Communication between threads needs `std::atomic`; concurrent reads and writes of an ordinary variable are a data race ([[intro.races]]) even with volatile.

C++20 deprecated several uses of volatile; the deprecation of compound assignment was later reverted. What the current draft still deprecates: increment and decrement of volatile objects, using the result of an assignment to a volatile object (as in `a = v = b`), volatile parameters and return types, and volatile structured bindings ([[depr.volatile.type]]).

## Elaborated type specifiers [dcl.type.elab]

```cpp run ok
struct T { int v; };
int main() {
    int T = 0;          // the variable T hides the class name T
    struct T obj{T};    // struct T finds the class; the T in {T} is the variable
    return obj.v;
}
```

An **elaborated-type-specifier** is a type name preceded by the keyword `class`, `struct`, `union` or `enum`. The first three keywords are collectively called the *class-key*. It has three uses:

1. Forward declaration: `struct S;`;
2. Introducing a not-yet-declared class name in passing within a declaration: `struct Node* next;`;
3. Referring to a class name hidden by a non-type name, as in the example above, or POSIX's `struct stat st;` (`stat` is also a function name).

¶5 is a note: lookup of the name in an elaborated type specifier considers only types ([[basic.lookup.elab]]), which is why use 3 works.

### Forward declarations (¶2)

¶2 A declaration that consists solely of an elaborated type specifier must be an explicit specialization, a partial specialization, an explicit instantiation, or one of the following two forms:

```text
class-key attribute-specifier-seq(opt) identifier ;
class-key attribute-specifier-seq(opt) simple-template-id ;
```

The first declares the identifier as a class name, i.e. a forward declaration; the second can only appear in an explicit specialization or partial specialization. The attributes appertain to the class being declared.

```cpp error
struct S;                  // OK: forward declaration
struct [[deprecated]] D;   // OK: the attribute appertains to D
namespace N { struct Inner; }
struct N::Inner;           // error: can't use a qualified name
enum E;                    // error: enum is not a class-key
enum class F : int;        // OK: this is an opaque enum declaration, not covered here
```

`struct N::Inner;` is forbidden because a declaration with a qualified name can only redeclare an existing entity: if `Inner` already exists, the line does nothing; if it doesn't, members can't be added to `N` from outside. A forward declaration of an unscoped enumeration must specify the underlying type (`enum E : int;`); see [[dcl.enum]].

### Where a class name declared in passing goes (¶3)

¶3 Elsewhere, an elaborated type specifier can't have attributes. If it is just an unqualified identifier and lookup of that identifier finds nothing, it declares the identifier as a class name (`enum` can't be used in this case). The target scope of the new class name is the nearest enclosing namespace or block scope:

```cpp run ok
void f(struct Fwd* p);     // the parameter scope is skipped: Fwd is declared in the global namespace
Fwd* r = nullptr;          // OK
struct List { struct Node* head; };   // class scope is skipped too
Node* n = nullptr;         // OK: Node is a global class, not List::Node
int main() {}
```

```cpp error
void g() { struct Q* q; (void)q; }   // Q is declared in g's block scope
Q* bad;                    // error: no Q at global scope
```

!!! pitfall "Different from C"
    In C, `struct Fwd` in `void f(struct Fwd* p);` is visible only in the function prototype scope, and a `struct Fwd` defined later at file scope is a different type, so `f` can't be called. C++ puts it in the enclosing namespace, avoiding this problem. On the other hand, the `Node` introduced by `struct Node* head;` in a class is not a nested class; for a nested class you must write `struct Node;` separately in the class.

### Friend declarations (¶4)

¶4 In a friend declaration `friend class X;`, the elaborated type specifier can only be a class-key plus a name (possibly qualified or with template arguments); it can't have attributes and can't use `enum`. Lookup of an unqualified name doesn't go beyond the nearest enclosing namespace or block scope; if nothing is found, the declaration introduces a class into that scope, but ordinary lookup won't find its name until a proper declaration appears ([[dcl.friend]]). Note 1 adds that using-directives in the target scope that nominate outer namespaces are ignored here.

```cpp run ok
namespace N {
    class X { friend class Helper; int secret = 7; };   // declares N::Helper
    class Helper { public: int peek(X& x) { return x.secret; } };   // the same class
}
int main() { N::X x; return N::Helper{}.peek(x) - 7; }
```

### Can't refer to a typedef name (¶6)

¶6 If the name resolves to a class name or enumeration name, the elaborated type specifier introduces that type just like a simple type specifier; if it resolves to a typedef name (including a specialization of an alias template), it is ill-formed. Note 3 points out that therefore, in a class template with type parameter `T`, `friend class T;` is ill-formed and `friend T;` is well-formed ([[class.friend]]).

```cpp error
struct S { };
typedef S TS;
struct TS* p;          // error: TS is a typedef name
template<class T> struct W { friend class T; };   // error
```

### The keyword must match the kind of class (¶7)

¶7 `enum` can only refer to an enumeration, `union` only to a union, and `class` and `struct` only to a non-union class, but those two are interchangeable.

<div class="compare" markdown="1">

```cpp run ok
enum class E { a, b };
enum E x = E::a;  // class can be omitted
struct S { } s;
class S* p = &s;  // class and struct are interchangeable
int main() {}
```

```cpp error
union U { };
struct U* pu;  // error: must use union
struct V;
enum V* pv;    // error: V is not an enumeration
int main() {}
```

</div>

!!! impl "MSVC and class/struct interchange"
    The standard allows mixing `struct S` and `class S`, but MSVC's name mangling encodes the class-key (`V` for `class`, `U` for `struct`). If one translation unit declares `class S` and another defines `struct S`, MSVC may produce link errors. Clang's `-Wmismatched-tags` warning flags this. The Itanium ABI doesn't encode the class-key.

## Pack indexing specifiers [dcl.type.pack.index] {{c++26}}

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);

template<class... Ts>
auto second(Ts... ts) {
    Ts...[1] x = ts...[1];   // type pack indexing + expression pack indexing
    return x;
}
int main() { return int(second(1, 2.5, 'c')) - 2; }
```

Through C++23, getting the Nth type of a pack required recursive templates or `std::tuple_element_t<N, std::tuple<Ts...>>`, both with significant compile-time cost. C++26 **pack indexing** ([[P2662]]) makes it a built-in language operation, written `P...[I]`. Expression pack indexing `ts...[1]` is covered in [[expr.prim.pack.index]].

¶1 `P` must be an identifier denoting a pack. ¶2 The subscript must be a converted constant expression of type `std::size_t`; its value V is called the **index** and must satisfy 0 ≤ V < `sizeof...(P)`. Out of range is ill-formed and an error at compile time:

```cpp error
template<class... Ts> using Bad = Ts...[2];
Bad<int, char> b;      // error: index 2 is out of range
```

¶3 A pack indexing specifier is itself a pack expansion ([[temp.variadic]]), so it can appear on its own without another `...`. The note in ¶4 says it denotes the type of the Vth element of the pack.

!!! lawyer "A syntax incompatibility with C++23"
    In C++23, `template<class... T> void f(T... [1]);` declares an unnamed function parameter pack, each parameter of type `T[1]` (adjusted to a pointer). C++26 parses `T...[1]` as pack indexing, so such code becomes ill-formed. The named form `void g(T... ptr[1]);` is unaffected ([[diff.cpp23.dcl.dcl]]).

## Type splicing [dcl.type.splice] {{c++26}}

```text
splice-type-specifier:
    typename(opt) splice-specifier
    typename(opt) splice-specialization-specifier
```

C++26 static reflection ([[P2996]]) uses `^^T` to obtain a reflection value (of type `std::meta::info`) and `[: r :]` to splice it back into code. This subclause specifies the cases where a splice yields a type. As of writing, Clang 23 doesn't implement static reflection; the examples in this section are taken from the standard and have not been verified by compiling.

```cpp
template<std::meta::info R> void tfn() {
    typename [:R:]::type m;       // OK: typename applies to the whole qualified name
}
struct S { using type = int; };
void fn() {
    [:^^S::type:] *var;           // error: here [: :] is an expression and the line is a multiplication
    typename [:^^S::type:] *var;  // OK: declares int* var
}
using alias = [:^^S::type:];      // OK: type-only context
```

¶1 gives two disambiguation rules. A splice immediately followed by `::` is never a type splice; it is part of a qualified name. A splice without `typename` is treated as a type only in a **type-only context** (for example the right-hand side of an alias declaration, see [[temp.res.general]]); elsewhere, `[: r :]` is an expression by default ([[expr.prim.splice]]). The reasoning is the same as for `typename` before dependent names: at parse time it isn't known whether `r` reflects a type or a value.

¶2 A type splice of the form `[: r :]` must designate a type, class template or alias template, and the result is that entity; when it designates a template, it is the CTAD placeholder of ¶3.3 above. ¶3 The form `[: r :]<args>` requires `r` to designate a class template or alias template, and the result is the specialization for those arguments.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[dcl.type.general] ¶4 is a note saying that class definitions, enumeration definitions and `typename` specifiers are covered in [[class]], [[dcl.enum]] and [[temp.res]] respectively.

[dcl.type.simple] ¶2 and [dcl.type.elab] ¶1 define **component names**: the qualifying parts, type names, template names, etc. appearing in the specifier. Clauses such as [[basic.lookup]] and [[module.reach]] use this concept to determine which names a declaration uses.

Note 1 in [dcl.type.cv] ¶1 points out that the effects of cv-qualifiers on object types and function types are covered in [[basic.type.qualifier]] and [[dcl.fct]] respectively.

</details>

## History

!!! history
    - C++98 removed C's implicit int and distinguished type specifiers from defining type specifiers.
    - C++11 added `char16_t`, `char32_t`, `long long`, `decltype`, and `auto` as a placeholder type.
    - C++17 added the CTAD placeholder; C++20 added `char8_t`, alias template CTAD and constrained placeholders `Concept auto`, and deprecated a set of volatile uses.
    - C++26 added pack indexing specifiers ([[P2662]]) and type splicing ([[P2996]]).

## Common misconceptions

!!! pitfall "`const_cast` lets you modify a const object"
    It compiles, but if the object itself is const, modifying it at run time is UB. `const_cast` is only safe when the access path is const and the object itself isn't.

!!! pitfall "`char` is `signed char`"
    They are distinct types, and the signedness of `char` is implementation-defined; on ARM Linux it is usually unsigned.

!!! pitfall "volatile can be used for thread synchronization"
    It can't. volatile provides no atomicity or inter-thread ordering; use `std::atomic`.

## Questions

!!! question "Question 1"
    Which of these are valid types? `unsigned`, `signed long long int`, `long signed`, `short unsigned int`, `long double long`, `unsigned signed char`.

<details markdown="1">
<summary>Answer</summary>

`unsigned` (i.e. `unsigned int`), `signed long long int` (i.e. `long long`), `long signed` (i.e. `long`) and `short unsigned int` (i.e. `unsigned short`) are all valid. `long double long` is invalid: once one `long` combines with `double`, the second `long` has nothing to combine with, and the standard has no `long long double`. `unsigned signed char` is invalid; `signed` and `unsigned` can't be combined ([[dcl.type.general#2]]).
</details>

!!! question "Question 2"
    In the code below, is the parameter type of `N::f` `::S*` or `N::S*`?

    ```cpp
    struct S { int x; };
    namespace N {
        void f(struct S* p);
        struct S { double y; };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It's `::S*`. When `f` is declared, lookup of `S` finds the global `::S`, and [[dcl.type.elab#3]] only declares a new class when lookup finds nothing. The `N::S` defined afterwards is a different class, unrelated to `f`. If the first line is removed, `struct S` declares `N::S` in the nearest enclosing namespace `N`, the later definition defines exactly that class, and the parameter type is `N::S*`.
</details>
