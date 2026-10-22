---
title: The typedef specifier
summary: "typedef and using alias declarations give an existing type another name without creating a new type; this subclause also covers the restrictions on combining typedef, where typedef names can't appear, and how the unnamed struct in typedef struct { … } S; borrows S for linkage."
updated: 2026-10-19
---

!!! tldr
    - `typedef` and `using X = …;` both declare type aliases: the alias and the original are the same type, so they can't be used for strong types.
    - `typedef` can only combine with type specifiers and can't be used in parameter declarations or function definitions; the `using` form can also be an alias template.
    - A typedef name can't be used in `struct T`, in a class definition, or in constructor and destructor declarations.
    - The unnamed struct in `typedef struct { … } S;` borrows `S` as its name for linkage. Since C++20 such a struct may only contain C-compatible members.

## An alias is not a new type (¶1)

```cpp run ok
#include <type_traits>
typedef int MILES, *KLICKSP;                 // MILES is int, KLICKSP is int*
typedef int ARR[3], (*FP)(MILES);            // an array type, a pointer-to-function type
MILES distance = 0;
extern KLICKSP metricp;
static_assert(std::is_same_v<MILES, int>);   // the same type
void f(int);
void f(MILES);                               // a redeclaration of the same function, not an overload
int main() { }
```

¶1 A declaration whose specifier sequence contains `typedef` declares a **type alias**. The name so declared is a *typedef-name*, and the type it denotes is the type the same declarator would get in an ordinary declaration. There's a simple way to read a typedef: remove `typedef` and what's left is a variable declaration; add `typedef` and the variable's name becomes a name for that variable's type. So the `*` in `*KLICKSP` above applies only to `KLICKSP`, and `MILES` is still `int`.

A typedef name doesn't introduce a new type the way a class declaration ([[class.name]]) or an enumeration declaration ([[dcl.enum]]) does. After `typedef int Meters; typedef int Seconds;`, both names are `int`, can be assigned to each other, and are not distinguished in overloading. If you need a strong type, define a new class or enumeration.

¶1 also specifies where `typedef` can appear:

- It can only combine with defining type specifiers (*defining-type-specifier*: type specifiers, class definitions, enumeration definitions), not with `static`, `inline`, `constexpr`, `friend` or any other specifier;
- It can't be used in a parameter declaration or a function definition;
- A declaration with `typedef` but no declarator (`typedef int;`) is ill-formed.

```cpp error
typedef static int SI;            // error: can't combine with a storage class specifier
typedef inline int II;            // error: nor with inline
void g(typedef int x);            // error: can't be used in a parameter declaration
typedef int h(int) { return 0; }  // error: can't be used in a function definition
```

For `typedef int;`, Clang 23 gives only a `-Wmissing-declarations` warning. A warning is a diagnostic too, and meets the standard's requirement.

!!! note "Repeated typedefs"
    At namespace or block scope, a name can be declared again with typedef as long as it denotes the same type (`typedef int I; typedef int I;` is valid). Repeating the same member typedef in a class definition is ill-formed, because a class member can't be declared twice in the class definition ([[class.mem.general#8]]).

## Alias declarations (¶2)

```cpp run ok
#include <vector>
using handler_t = void (*)(int);
extern handler_t ignore;
extern void (*ignore)(int);         // OK: a redeclaration of the same variable, same type
template<class T> using Vec = std::vector<T>;   // alias template
using Old [[deprecated("use New")]] = int;      // the attribute appertains to the alias itself
int main() { Vec<int> v; return int(v.size()); }
```

¶2 An **alias declaration** (*alias-declaration*) `using identifier attributes(opt) = type;` declares a type alias with exactly the same semantics as `typedef`. The identifier after `using` is not looked up; it simply becomes the typedef name, and an attribute directly after the identifier appertains to the alias.

The `using` form has two advantages. First, the name is on the left and the type on the right, which makes function pointer types easier to read: `using handler_t = void (*)(int);` versus `typedef void (*handler_t)(int);`. Second, it can be put in a template declaration to become an **alias template** ([[temp.alias]]), which `typedef` can't do. Conversely, `typedef` can define several aliases in one declaration, and `using` can't.

The name introduced by an alias declaration is not visible until the end of the whole declaration ([[basic.scope.pdecl]]), so an alias can't refer to itself in its definition:

```cpp error
template<class T> struct P { };
using cell = P<cell*>;            // error: cell can't be found here yet
```

`typedef P<cell*> cell;` doesn't work either, because the point of declaration of `cell` is after its declarator, and `P<cell*>` comes before the declarator. A recursive type can only be expressed with a class: `struct cell { P<cell*> p; };`.

¶2 Its last sentence says that a class or enumeration can't be defined in the type of an alias template:

```cpp error
template<class T> using Box = struct { T t; };   // error: can't define a class in an alias template
```

Each specialization of an alias template equals the type it denotes. If a class were defined there, there would be no way to specify which class `Box<int>` and `Box<long>` each are, what scope they belong to, or what their linkage names are. The non-template `using A = struct { int t; };` doesn't have this problem and is valid.

## Where typedef names can't appear (¶3)

```cpp error
struct S { S(); ~S(); };
typedef struct S T;
S a = T();                // OK: using T as a type is fine
struct T* p;              // error: a typedef name can't be used in an elaborated type specifier
struct T { };             // error: can't define a class through a typedef name
```

¶3 Note 1 lists four places where a typedef name can't be used to refer to a class:

| Position | Example (`T` is a typedef name) | Explanation |
|---|---|---|
| Elaborated type specifier | `struct T* p;` | `struct` and `class` must be followed by a class name ([[dcl.type.elab#6]]) |
| Class definition | `struct T { };` | Can't define a class through an alias |
| Constructor declaration | `T();` inside the class | Constructors are declared with the injected-class-name ([[class.ctor.general]]) |
| Destructor declaration | `~T();` inside the class | Likewise; destructor names have their own lookup rules ([[class.dtor]]) |

A typedef name can be used as a qualifier, as long as the constructor's own name is still the class name:

```cpp run ok
struct S { S(); };
typedef S T;
T::S() { }                // OK: qualified with T, the constructor name is S
int main() { T t; (void)t; }
```

¶3 The normative text also says that a *simple-template-id* (a template name plus arguments, like `X<int>`) is a typedef name only if the template name names an alias template or a type template template parameter; something like `std::vector<int>`, which denotes a class template specialization, is a class name.

## Unnamed structs borrow a typedef name for linkage (¶4)

C headers are full of this:

```cpp
typedef struct { int x, y; } Point;
void draw(Point p);       // a function with external linkage whose parameter is an unnamed struct
```

`draw` has external linkage, so the `draw` in each translation unit (TU: a separately compiled source file together with the headers it includes) has to match up. But its mangled name must encode the parameter type, and this struct has no name.

¶4 The solution: if an unnamed class or unnamed enumeration C is defined in a typedef declaration, the first typedef name in that declaration whose type is exactly C is the **typedef name for linkage purposes** of C ([[g:typedef-name-for-linkage]]). C borrows this name for linkage ([[basic.link#4]]). Under the Itanium ABI, the mangled name of `draw` is `_Z4draw5Point`.

A few details:

- It must be the first name whose type is exactly C. In `typedef struct { } *ps, S;`, the type of `ps` is `C*`, so the linkage name is `S`.
- The class must be defined in that typedef declaration. `typedef decltype([]{}) C;` doesn't define the closure type (the closure type is defined by the lambda expression), so the closure type gets no linkage name (note 2).
- An unnamed enumeration can also borrow its first enumerator for linkage ([[dcl.enum]]).

!!! lawyer "Do alias declarations count?"
    ¶4 literally talks about typedef declarations, while `using A = struct { … };` is an alias declaration. But paragraph 2 says the two have the same semantics, and both Clang and GCC treat `A` as the linkage name. With Clang 23, the symbol of `f` in `using A = struct { int t; }; void f(A) { }` is `_Z1f1A`.

## C++20: only C-compatible structs (¶5)

```cpp error
typedef struct {
    int f() { return 0; }   // error: member function
} X;
struct B { };
typedef struct : B { } Y;                 // error: base class
typedef struct { int m = 1; } Z;          // error: default member initializer
typedef struct { decltype([]{}) m; } W;   // error: contains a lambda expression
```

¶5 An unnamed class with a typedef name for linkage purposes shall not:

- ¶5.1 declare any members other than non-static data members, member enumerations, or member classes, i.e. no member functions, static data members, member typedefs, `static_assert`, and so on;
- ¶5.2 have any base classes or default member initializers;
- ¶5.3 contain a lambda expression.

Its member classes must also meet these requirements, recursively. A C-style struct like the following is unaffected:

```cpp run ok
typedef struct {
    int x, y;
    enum Kind { a, b } kind;      // OK: member enumeration
    struct Inner { int z; } in;   // OK: member class, which itself meets the requirements
} CStyle;
int main() { CStyle c{}; return c.x; }
```

Why the restriction? When the compiler reads `typedef struct {`, it doesn't yet know a typedef name will follow, so it doesn't know whether this class has linkage or what it is called. The mangled names of member functions include the class name, the identity of a lambda's closure type depends on the enclosing entity, and default member initializers may contain lambdas too. If the class body contained such things, the compiler would have to go back and revise decisions it had already made; for modules, this also affects whether a declaration can be exported. C++20's [[P1766R1]] simply restricts this form to what C supports, and C compatibility is the very reason this feature exists.

!!! impl "Clang only warns"
    For code violating paragraph 5, Clang 23 gives only a `-Wnon-c-typedef-for-linkage` warning ("anonymous non-C-compatible type given name for linkage purposes by typedef declaration; add a tag name here") and keeps compiling, for compatibility with lots of old code. By the standard all such code is ill-formed. The fix is what the message says: give the struct a name (`typedef struct X { … } X;`); then it's no longer an unnamed class and paragraph 5 doesn't apply.

!!! history "History"
    - C++98 already had `typedef` and the typedef name for linkage purposes, with no restrictions on the contents of the unnamed class.
    - C++11 added alias declarations and alias templates.
    - C++20 added the restrictions of paragraph 5 ([[P1766R1]]). At the same time lambdas became allowed in unevaluated operands, which made `typedef decltype([]{}) C;` possible; note 2 says it gives the closure type no linkage name.

!!! pitfall "Common misconceptions"
    - typedef is textual substitution: it isn't. In `typedef char* P; const P p = nullptr;`, the type of `p` is `char* const`, not `const char*` ([[dcl.spec.general#3]]).
    - `using` can do more than `typedef`: apart from alias templates, they are exactly equivalent.
    - typedef can create strong types: it can't; the alias and the original are the same type.

!!! question "Question"
    Is the following code well-formed in C++20? If not, what is the smallest fix?

    ```cpp
    typedef struct {
        static constexpr int version = 1;
        int data;
    } Header;
    ```

<details markdown="1">
<summary>Answer</summary>

Ill-formed: a static data member is not a non-static data member, member enumeration or member class (¶5.1). In fact an unnamed class can't have static data members anyway ([[class.static.data#2]]), and Clang 23 reports an error for this directly.

The smallest fix is to name the struct: `typedef struct Header { … } Header;`, or simply `struct Header { … };`. A named class isn't subject to paragraph 5. If the struct is also meant for C, move `version` out and make it a macro or a namespace-scope constant.
</details>
