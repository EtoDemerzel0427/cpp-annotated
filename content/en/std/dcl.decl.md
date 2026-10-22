---
title: Declarators
summary: "How a declaration is made up of specifiers and declarators, how to read declarators of any complexity, and the rules for type-ids, trailing return types, trailing requires-clauses and declarations with qualified names."
updated: 2026-10-19
---

!!! tldr
    - A declaration consists of a specifier sequence and one or more comma-separated declarators. `*`, `&`, `[]` and `()` belong to their own declarator, so the `b` in `int* a, b;` is an `int`.
    - Operators in declarators have the same precedence as in expressions: postfix `[]` and `()` bind tighter than prefix `*` and `&`. Parentheses only change grouping, not the type.
    - To read a complex declarator, peel operators from the outermost inwards, or start at the name and read right first, then left.
    - A *type-id* is a declaration with the name omitted, and the position where the name would go is uniquely determined.
    - A declaration with a qualified name (`void N::f() {}`) can't introduce a new member; function declarations and `extern` declarations at block scope declare members of the enclosing namespace.

## Specifiers and declarators [dcl.decl.general]

```cpp
const int *p, a[3], f(int);
```

This declaration has two parts. The leading `const int` is the **decl-specifier-seq** (see [[dcl.spec]]), which gives a base type plus attributes like storage duration and linkage. The comma-separated `*p`, `a[3]` and `f(int)` that follow are three **declarators** ([[g:declarator|declarator]]).

¶1 Each declarator declares one entity: a variable, function or type.

¶2 A declarator optionally names the entity and modifies the type given by the specifiers with operators such as `*` (pointer to) and `()` (function returning). So the above declares `p`, a pointer to `const int`; `a`, an array of 3 `const int`; and `f`, a function taking `int` and returning `const int`.

A declarator can be followed by an initializer ([[dcl.init]]); the combination is called an *init-declarator*. A declarator with the name omitted is an **abstract-declarator** ([[g:abstract-declarator|abstract-declarator]]); it appears in unnamed parameters, *type-id*s and exception declarations. To read one, imagine a unique identifier at the position where the name would go (see the [dcl.name] section below).

### Multiple declarators are analyzed one by one (¶3)

¶3 Each declarator in a declaration is analyzed separately, as if it were in a declaration by itself. So `T D1, D2;` is usually equivalent to `T D1; T D2;`.

!!! pitfall "The `b` in `int* a, b;` is not a pointer"
    `*` belongs to the declarator `*a`, not to the specifiers. The only specifier is `int`, so `b` is an `int`. For two pointers, write `*` on each declarator, or define an alias first: `using IP = int*; IP a, b;`. Then `IP` is the specifier and both are pointers.

Note 2 in the standard points out two exceptions to the usual equivalence. The first is when a name introduced by a declarator hides a type name in the specifiers:

<div class="compare" markdown="1">

```cpp run ok
struct S { };
void f() {
  S S, T;  // two objects of type S
  (void)S; (void)T;
}
```

```cpp run error
struct S { };
void f() {
  S S;
  S T;     // error: S is now a variable name
}
```

</div>

The specifier `S` is looked up only once, at the start of the declaration, when it is still a class name. Split into two declarations, the second one looks up `S` again and finds the variable just declared.

The second exception is `auto`: all declarators in the same declaration must deduce the same type ([[dcl.spec.auto]]).

```cpp run error
auto i = 1, j = 2.0;   // error: i deduces int, j deduces double
```

Still, looking up the specifiers only once doesn't mean later declarators can't see earlier names. Array bounds and initializers inside a declarator are parsed after the earlier names are already visible:

```cpp run ok
const int n = 3, a[n] = {1, 2, 3};   // the n in a[n] is the n just declared
int main() { return a[0] - 1; }
```

Here `a` has type `const int[3]`; `const` applies to it too, so it must have an initializer.

## Declarator grammar and precedence [dcl.decl.general]

### Declaration mirrors use

C's declarator grammar follows the principle that **declaration mirrors use**. `int *p` means `*p` is an `int`; `int a[3]` means `a[i]` is an `int`; `int f(int)` means calling `f` with an `int` gives an `int`.

Operators in declarators have the same precedence as the same operators in expressions: postfix `()` and `[]` bind tighter than prefix `*`. So these two declarations are completely different:

<div class="compare" markdown="1">

```cpp
int *f();     // f is a function returning int*
int *a[3];    // a is an array whose elements are int*
```

```cpp
int (*f)();   // f is a pointer to a function returning int
int (*a)[3];  // a is a pointer to int[3]
```

</div>

### The grammar itself encodes precedence (¶7)

¶7 Here is the core of the declarator grammar, with attributes omitted:

```
declarator:
    ptr-declarator
    noptr-declarator parameters-and-qualifiers trailing-return-type
ptr-declarator:
    noptr-declarator
    ptr-operator ptr-declarator                     // prefix: * & && C::*
noptr-declarator:
    declarator-id
    noptr-declarator parameters-and-qualifiers      // postfix: (params) cv ref noexcept
    noptr-declarator [ constant-expression(opt) ]   // postfix: [N]
    ( ptr-declarator )                              // parentheses
```

Three conclusions can be read directly from this grammar:

1. Postfix operators can only attach to a *noptr-declarator*, and prefix operators only to a *ptr-declarator*. So `*a[3]` can only parse as `*(a[3])`: the postfix binds first.
2. To make a prefix operator bind first, a *ptr-declarator* must be wrapped in parentheses to form a *noptr-declarator*, as in `(*a)[3]`.
3. *trailing-return-type* only appears in the production for the top-level *declarator*, so a trailing return type can only be written on the outermost function declarator.

The other parts: *parameters-and-qualifiers* is the suffix of a function declarator, comprising the parameter list, cv-qualifiers, ref-qualifier and `noexcept` (see [[dcl.fct]]). A *ptr-operator* is `*`, `&`, `&&` or `C::*`; `*` and `C::*` can be followed by cv-qualifiers, `&` and `&&` can't ([[dcl.ref]]). The *declarator-id* is the name being declared; it can be preceded by `...` (declaring a function parameter pack), and the name itself can be a qualified name, an operator function name, a *template-id*, etc.

## Reading the type off a declarator [dcl.meaning.general]

### Specifiers apply to every name (¶4)

¶4 Specifiers such as `static`, `extern`, `thread_local`, `inline`, `constexpr` and `typedef` apply directly to every name in the declaration; the type of each name is determined jointly by the specifier sequence and its own declarator.

```cpp run ok
static int a, *b, c[2];        // all three are static
typedef int I, *IP, A3[3];     // three aliases: int, int*, int[3]
static_assert(sizeof(A3) == 3 * sizeof(int));
int main() { (void)b; (void)c; return a; }
```

### Computing the type recursively (¶5–8)

¶5 For each declarator, the declaration can be seen as having the form `T D`, where `T` is the specifier sequence and `D` the declarator. The standard computes the type of the name in `D` by a recursive procedure.

¶6 First, the specifier sequence determines a type `T`. The order of specifiers doesn't matter: the `int unsigned` in `int unsigned i;` determines `unsigned int` ([[dcl.type.simple]]).

¶7 If `D` is just a name, its type is `T`.

¶8 If `D` has the form `( D1 )`, the type is the same as in `T D1`. Parentheses don't change the type, only the grouping of complex declarators. So `int (x);` is just `int x;`, and all the ambiguities in [[dcl.ambig.res]] stem from this.

The remaining forms are defined by the following subclauses, all with the same pattern. If the type of the name in `T D1` is "[inner modifiers] `T`", then:

| Form of `D` | Type of the name in `D` | Subclause |
|---|---|---|
| `* cv D1` | [inner modifiers] cv pointer to `T` | [[dcl.ptr]] |
| `& D1` / `&& D1` | [inner modifiers] lvalue / rvalue reference to `T` | [[dcl.ref]] |
| `C::* cv D1` | [inner modifiers] cv pointer to member of `C` of type `T` | [[dcl.mptr]] |
| `D1 [N]` | [inner modifiers] array of `N` `T` | [[dcl.array]] |
| `D1 ( params ) cv ref noexcept` | [inner modifiers] function taking these parameters and returning `T` | [[dcl.fct]] |

The standard calls [inner modifiers] the *derived-declarator-type-list*. In other words, the phrase contributed by the outermost operator sits right next to `T`, and the further in an operator is, the earlier its phrase comes.

### Reading a declarator by hand

Unrolling the recursion gives a manual method: find the outermost operator of `D`; its phrase goes right next to the current result; repeat on the remaining inner declarator until only the name is left. When deciding which is outermost, prefix operators are further out than postfix ones, and a pair of parentheses counts as one unit.

Take `int (*(*f)(int))[3];` as an example:

| Step | Current `D` | Outermost operator | Accumulated type |
|---|---|---|---|
| 1 | `(*(*f)(int))[3]` | Postfix `[3]` (the parentheses are one unit) | array of 3 `int` |
| 2 | `*(*f)(int)` | After removing the parentheses, the outermost is prefix `*` | pointer to [array of 3 `int`] |
| 3 | `(*f)(int)` | Postfix `(int)` | function taking `int` and returning [pointer to `int[3]`] |
| 4 | `*f` | Prefix `*` | pointer to [the function in the previous row] |
| 5 | `f` | Only the name is left | |

So `f` is a function pointer; the function it points to takes `int` and returns a pointer to `int[3]`.

Another common method is the **right-left rule**, which is the same process in reverse: start at the name, read postfix operators to the right; on hitting a right parenthesis, turn and read prefix operators to the left; on hitting a left parenthesis, leave that pair of parentheses and continue to the right. The phrases come out in natural-language order.

You can also read by "declaration mirrors use": what must `f` be for `(*(*f)(5))[2]` to be an `int`? `*f` can be called, so `f` points to a function; the call result can be dereferenced, so the function returns a pointer; after dereferencing it can be subscripted, so that pointer points to an array.

```cpp run ok
#include <type_traits>

int (*(*f)(int))[3];
using A3  = int[3];
using Fn  = A3*(int);          // function taking int and returning int(*)[3]
static_assert(std::is_same_v<decltype(f), Fn*>);

// signal: takes an int and a function pointer, returns a function pointer
void (*signal(int, void (*)(int)))(int);
auto signal2(int, void (*)(int)) -> void (*)(int);
static_assert(std::is_same_v<decltype(signal), decltype(signal2)>);

int (*arr[2])(int);            // array of 2 function pointers
static_assert(std::is_same_v<decltype(arr), int (*[2])(int)>);

int main() { }
```

!!! pitfall "Adding `const` to an alias is not text substitution"
    In `typedef int *IP; const IP p;` the type of `p` is `int *const`, not `const int *`. The `const` qualifies the whole type `IP` given by the specifiers, i.e. the pointer itself.

## type-id: a declaration with the name omitted [dcl.name]

### The name's position is unique (¶1)

Places like `sizeof`, `new`, casts, template arguments and `using` aliases need a type written on its own; the form used is a [[g:type-id|type-id]].

¶1 Syntactically, a type-id is a declaration for an entity that omits the name: specifiers plus an abstract declarator.

In an abstract declarator, the position where the name would go is uniquely determined. Putting the name back gives an ordinary declaration, and the type of the name is the type the type-id denotes:

| type-id | Name put back | Type |
|---|---|---|
| `int *` | `int *pi` | pointer to `int` |
| `int *[3]` | `int *p[3]` | array of 3 `int*` |
| `int (*)[3]` | `int (*p3i)[3]` | pointer to `int[3]` |
| `int *()` | `int *f()` | function with no parameters returning `int*` |
| `int (*)(double)` | `int (*pf)(double)` | pointer to function taking `double` and returning `int` |

How to find the position: the name goes after all prefix operators and before all postfix operators, inside the innermost pair of parentheses that isn't a parameter list. For example, the innermost parentheses of `int (*(*)(int))[3]` are `(*)`; putting the name after the `*` gives `int (*(*f)(int))[3]`. Compilers print types in diagnostics in exactly this type-id form, so learning to read it helps with reading diagnostics too.

The note in ¶2 reminds us that a type can also be named by a *typedef-name* ([[dcl.typedef]]).

### nofun-type-id

The current draft also defines [[g:nofun-type-id|nofun-type-id]]: a type-id whose outermost part is not a function declarator. `int()` and `auto() -> int` are not nofun-type-ids; `int(*)()` and `int(&)()` are. This is new wording after C++23.

`sizeof`, `alignof`, C-style casts `(T)e`, `new (T)` and trailing return types all switched to nofun-type-id. Function types could never appear in these places anyway. After the switch, `sizeof(int())` can no longer be read as a function type, only as an expression, so a formerly ill-formed form becomes well-formed; see [[dcl.ambig.res#2]]. `typeid(…)` and template arguments still use type-id, because function types are meaningful there, as in `std::function<int()>`.

## Trailing return types [dcl.decl.general]

`auto f(params) -> R` declares a function returning `R`. Per [[dcl.fct#1.3]], this form requires the specifier to be exactly `auto` on its own. It solves two problems:

1. A function returning a function pointer or array pointer doesn't have to split its return type in two around the name; compare `signal` and `signal2` above.
2. Since the return type comes after the parameters, it can use them (`decltype(t + u)`); when defining a member function outside the class, it is already in the class's scope and can use member type names directly.

```cpp run ok
struct C {
  using size_type = unsigned;
  size_type n() const;
  auto m() const -> size_type;
};
C::size_type C::n() const { return 1; }     // leading: must write C::size_type
auto C::m() const -> size_type { return 0; } // trailing: already in C's scope

template<class T, class U>
auto add(T t, U u) -> decltype(t + u) { return t + u; }

auto (*fp)(int) -> long = nullptr;          // function pointers can use the trailing form too

int main() { return add(1, 2L) == 3 && C{}.m() == 0 ? 0 : 1; }
```

```cpp run error
auto *g() -> int;   // error: the specifier must be auto on its own
```

## Initializers, requires-clauses and contract specifiers [dcl.decl.general]

The grammar in ¶1 gives two forms of *init-declarator*: a declarator followed by an initializer; or a declarator followed by an optional trailing requires-clause and optional function contract specifiers. The latter two only make sense for functions, so they never occur together with an initializer.

### When an initializer can be written (¶4)

This paragraph needs two terms first ([[basic.scope.scope]]). A declaration **inhabits** the scope it is written in. The scope into which the name is introduced and to which the entity belongs is the declaration's **target scope** ([[g:target-scope|target scope]]), usually the scope it inhabits. The **host scope** is defined as: if the declaration inhabits a block scope, that block scope; otherwise, the target scope.

¶4 A declarator can have an initializer only if it declares a variable and the declaration's host scope is the same as its target scope. This excludes two kinds of cases:

- What is declared is not a variable, e.g. a function. The `= 0` in `virtual void f() = 0;` is a *pure-specifier*, part of the grammar for class member declarations, not an initializer.
- A block-scope `extern` declaration. It inhabits the block, so its host scope is that block; but its target scope is the enclosing namespace (see item 3.5 below), and the two differ.

<div class="compare" markdown="1">

```cpp run ok
void f() {
  static int x = 1;  // host = target = block
  (void)x;
}
```

```cpp run error
int x;
void f() {
  extern int x = 1;  // error
}
```

</div>

A block-scope `extern int x;` refers to a namespace variable defined elsewhere. Giving it an initializer in the block would amount to defining a namespace-scope variable inside a function body, so it isn't allowed. By contrast, the out-of-class definition of a static data member `int A::s = 2;` inhabits namespace scope and its host scope is its target scope (the scope of class `A`), so it can be initialized.

### Trailing requires-clauses (¶5)

¶5 A requires-clause written after a declarator is a **trailing *requires-clause***, and it can only appear on a declarator that declares a **templated function** ([[temp.pre]]). Templated functions are not just function templates; they include member functions of class templates, call operators of generic lambdas, and other functions inside templated entities. The most common use is enabling an ordinary member function conditionally on the class template arguments:

```cpp run ok
#include <type_traits>

template<class T>
struct Box {
  T value;
  void increment() requires std::is_arithmetic_v<T> { ++value; }
};

int main() {
  Box<int> b{1};
  b.increment();          // OK
  Box<void*> p{nullptr};  // OK: as long as increment isn't called
  (void)p;
}
```

Example 1 in the standard lists the positions where it isn't allowed:

```cpp run error
void f1(int a) requires true;                 // error: not a templated function
template<typename T>
  auto f2(T a) -> bool requires true;         // OK
template<typename T>
  auto f3(T a) requires true -> bool;         // error: must come after the trailing return type
void (*pf)() requires true;                   // error: constrains a variable
void g(int (*)() requires true);              // error: constrains a parameter
auto* p = new void(*)(char) requires true;    // error: not a function declaration
```

A trailing requires-clause is not part of the function type ([[dcl.fct#13]]), but it is compared when deciding whether two declarations correspond (declare the same entity, [[basic.scope.scope]]). So two member functions differing only in their trailing requires-clauses are two overloads, and overload resolution chooses by partial ordering of constraints ([[temp.constr.order]]).

### Contract specifiers (¶6) {{c++26}}

¶6 Function contract specifiers `pre(…)` and `post(…)` can only appear on a declarator that declares a function; see [[dcl.contract.func]].

## Names and target scopes [dcl.meaning.general]

### declarator-id (¶1)

¶1 A declarator contains exactly one *declarator-id*, which is the name being declared. If the name is a *template-id* (such as `f<int>`), the declaration must be a template declaration, explicit specialization or explicit instantiation:

```cpp run error
template<class T> void tf(T);
void tf<int>(int);              // error: needs template<>
template<> void tf<int>(int);   // OK: explicit specialization
```

When the name is not an ordinary identifier (`operator+`, `operator int`, `~C`, `operator""_x`), the declaration declares the corresponding special function ([[class.conv.fct]], [[class.dtor]], [[over.oper]], [[over.literal]]). Attributes immediately following the name appertain to the entity declared; attributes after `*` appertain to the pointer type, and after `[]` to the array type.

### Declaring with a qualified name (¶3.1–3.4)

```cpp run error
namespace Q {
  namespace V { void f(); }
  void V::f() { }        // OK
  void V::g() { }        // error: g is not yet a member of V
  namespace V { void g(); }
}
namespace R {
  void Q::V::g() { }     // error: R doesn't enclose Q
}
```

¶3.1 If the name is qualified, the declaration must inhabit a namespace scope; `void N::f() {}` can't be written in a function body or a class.

¶3.4 In this case no new name is looked up; instead the declarator must correspond to one or more existing declarations in the scope the qualified name designates, and the target scope is the target scope of those declarations. In other words, a qualified name can only redeclare or define existing members, not introduce new ones.

The error in `R` comes from another requirement in [[basic.scope.scope]]: a qualified declaration must appear in a scope that encloses the target namespace, and `R` doesn't enclose `Q::V`.

¶3.3 Explicit instantiations, partial specializations and explicit specializations don't bind names. When identifying which function template specialization they declare, only lookup results that are **nominable** in the scope designated by the qualified name are considered. In the standard's Example 1, the `P::f` introduced by `using P::f` is not nominable in `N`, so `template<> void N::f(int*)` specializes the version in the inline namespace `O`.

### Block-scope function declarations and extern declarations (¶3.5)

¶3.5 If a declaration inhabits a block scope and declares a function or uses `extern`, its target scope is the innermost enclosing namespace, but the name is bound only in that block. Such a declaration can't be attached to a named module.

```cpp run error
namespace X {
  void p() {
    q();               // error: q not yet declared
    extern void q();   // q is a member of X; the name is visible only in p's block
    extern void r();   // r is also a member of X
  }
  void middle() {
    q();               // error: q isn't found here
  }
  void q() { }         // definition of X::q
}
void X::r() { }        // error (standard Example 3): r can't be declared with a qualified name
```

The last line violates item 3.4: a block-scope `extern` declaration is not nominable in `X`, so the qualified name finds no declaration to correspond to. As of writing, Clang 23 accepts this line without a diagnostic.

`void helper();` written in a block also declares a function of the enclosing namespace. It can't be defined in the block ([[dcl.fct.def.general#2]]) and can't be an abbreviated function template ([[dcl.fct#25]]). Combined with the rules of [[dcl.ambig.res]], `T x();` in a block becomes exactly such a function declaration; this is the so-called [[g:most-vexing-parse|most vexing parse]].

### Friend declarations (¶2)

¶2.1 The declarator of a friend declaration doesn't bind a name. So a friend function declared or defined only inside a class (a hidden friend) can't be found by ordinary lookup, only by argument-dependent lookup (ADL):

```cpp run error
struct N {
  friend void hf(N) { }   // target scope is the global namespace, but no name is bound
};
void use()  { hf(N{}); }      // OK: ADL finds it in the associated class N
void use2() { auto p = &hf; } // error: ordinary lookup doesn't find hf
```

The other rules depend on the form of the name:

- ¶2.3 The name is neither qualified nor a *template-id*: the name isn't looked up, and the target scope is the innermost enclosing namespace. If the friend declaration is in a local class, it must correspond to a reachable declaration in the innermost block scope.
- ¶2.2 The name is qualified (`friend void N::f(int);`) or a *template-id* (`friend void g<>(int);`): the name is looked up, and the declarator must correspond to at least one of the declarations found; those declarations all have the same target scope, which is also the friend declaration's target scope. So a qualified friend declaration can't declare a new function in passing either.

In the lookup of item 2.2, if the friend declaration is not itself a template declaration, the results are filtered first: if the name is a *template-id*, all non-template functions are discarded (item 2.2.1.1); otherwise, if the declarator corresponds to some non-template function found, all function templates are discarded (item 2.2.1.2); each remaining function template is replaced by a concrete specialization through deduction ([[temp.deduct.decl]]), and those for which deduction fails are discarded (item 2.2.1.3).

## Implementation notes

!!! impl
    C++'s declaration grammar needs to know whether a name is a type in order to parse: `a * b;` can be a multiplication or a declaration of a pointer `b`. GCC and Clang both use tentative parsing: on meeting a token sequence that could be a declaration, they first try to parse it as a declaration and fall back to an expression if that fails. The rules of [[dcl.ambig.res]] specify exactly this choice.

## History

!!! history
    - The declarator grammar is inherited from C. C++ added references `&`, pointers to members `C::*`, and cv-qualification on function declarators (for member functions).
    - C++11 added trailing return types, rvalue references `&&`, ref-qualifiers, `noexcept`, attributes, and `...` for declaring parameter packs.
    - C++20 added trailing requires-clauses and abbreviated function templates ([[dcl.fct#23]]).
    - C++26 added function contract specifiers ([[dcl.contract.func]]).
    - The draft after C++23 introduced *nofun-type-id*.

## Questions

!!! question "Question 1"
    Write out the type of `foo` in `extern char *(*(**foo[][8])())[];`, and break it into readable pieces with `using` aliases.

<details markdown="1">
<summary>Answer</summary>

Peel from the outside in. The whole declarator is `*(*(**foo[][8])())[]`.

1. The outermost is the leading prefix `*`: pointer to `char`, i.e. `char*`.
2. Left with `(*(**foo[][8])())[]`, the outermost is postfix `[]`: array of unknown bound of `char*`.
3. Left with `*(**foo[][8])()`, the outermost is prefix `*`: pointer to [array of unknown bound of `char*`].
4. Left with `(**foo[][8])()`, the outermost is postfix `()`: function with no parameters returning [the pointer from the previous step].
5. Left with `**foo[][8]`, two prefix `*`: pointer to [pointer to that function].
6. Left with `foo[][8]`: array of unknown bound whose elements are arrays of 8 [pointers from the previous step].

```cpp run ok
using CPArr = char*[];      // array of unknown bound of char*
using Fn    = CPArr*();     // function returning a pointer to it
using Elem  = Fn**;         // pointer to function pointer
extern Elem foo[][8];
extern char *(*(**foo[][8])())[];   // the same type; redeclaration succeeds
int main() { }
```

`extern` is required here: a variable of array-of-unknown-bound type without an initializer can only be declared, not defined ([[dcl.array#7]]).
</details>

!!! question "Question 2"
    In `template<class T> struct S { void f() requires true; };`, `f` is not a function template. Why can it have a trailing requires-clause? Does the type of `S<int>::f` include this constraint?

<details markdown="1">
<summary>Answer</summary>

¶5 requires a templated function. Per [[temp.pre]], a member function of a class template is a templated entity, so it is allowed. Constraints are not part of the function type ([[dcl.fct#13]]); the type of `S<int>::f` is just `void()`. The constraint only affects whether the function is viable in overload resolution and whether two declarations correspond.
</details>
