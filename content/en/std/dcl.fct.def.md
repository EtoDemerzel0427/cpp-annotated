---
title: Function definitions
summary: "What a function definition consists of and where it may appear; __func__, available automatically in every function body; which functions can be = default, and how defaulting inside and outside the class differ; how = delete takes part in overload resolution; and how a program replaces replaceable functions such as operator new."
updated: 2026-10-19
---

!!! tldr
    - Functions can only be defined at namespace or class scope; the parameter and return types at the definition must be complete, except for deleted functions.
    - `= default` can only be used for special member functions, comparison operators, and postfix `++`/`--`. A function defaulted on its first declaration in the class is not user-provided and can be trivial; one defaulted outside the class is user-provided, and the type loses triviality.
    - A `= delete` function takes part in overload resolution as usual, and selecting it is ill-formed, even in unevaluated operands such as `sizeof` and `decltype`. A deleted definition must be the function's first declaration.
    - Since C++26 you can write `= delete("reason")`, and the reason text appears in the diagnostic.
    - For replaceable functions such as global `operator new`/`operator delete`, the program provides a single definition that replaces the implementation's version; a replacement function can't be `inline`, and must have C++ language linkage and be attached to the global module.

## What a function definition consists of ([dcl.fct.def.general])

```cpp
int max(int a, int b, int c) {
  int m = (a > b) ? a : b;
  return (m > c) ? m : c;
}
```

In Example 1 in the standard, `int` is the *decl-specifier-seq*, `max(int a, int b, int c)` is the *declarator*, and the braced part is the *function-body*. The grammar given in ¶1 can be summarized as:

```text
function-definition:
    attribute-specifier-seq(opt) decl-specifier-seq(opt) declarator virt-specifier-seq(opt) contract-specifiers(opt) function-body
    attribute-specifier-seq(opt) decl-specifier-seq(opt) declarator requires-clause contract-specifiers(opt) function-body
function-body:
    ctor-initializer(opt) compound-statement
    function-try-block
    = default ;
    = delete ;
    = delete ( unevaluated-string ) ;
```

¶1 also specifies a few things:

- The specifier sequence can be omitted; constructors, destructors and conversion functions have none.
- A definition with `override`/`final` (*virt-specifier-seq*) must be a class member declaration; a definition with a *requires-clause* must define a templated function.
- Leading attributes appertain to the function. Contract specifiers `pre`/`post` ([[dcl.contract]]) go before the function body.
- When the standard speaks informally of a function body, it means the non-terminal *function-body*. For a constructor, this also includes the default member initializers or default-initialization used to initialize bases and members not given a *mem-initializer*. So "an exception thrown in a constructor body" also covers exceptions thrown during these member initializations.

¶2 In a function definition, `void declarator ;` or `declarator ;` must be a well-formed function declaration ([[dcl.fct]]). A function can only be defined at namespace scope or class scope; a lambda is an expression, not a function definition. Unless the function is deleted, the parameter types and return type at the definition can't be class types that are incomplete or abstract within the function body.

```cpp error
struct Inc;
Inc make();                     // OK: a declaration can use an incomplete type
Inc make() { return {}; }       // error: incomplete return type in the definition
Inc oops(Inc) = delete;         // OK: deleted functions are exempt
void outer() {
  void inner() { }              // error: a function can't be defined at block scope
}
```

A deleted function is never called, so the layout of its parameters and return value need not be known. This way, a deleted overload meant to block some kind of call can be declared for a type that is still incomplete.

¶3–¶6 are examples and notes: ¶4 says a *ctor-initializer* is only for constructors ([[class.base.init]]); Note 1 says the cv-qualifiers on a member function declarator determine the type of `this` in the body ([[expr.prim.this]]); Note 2 says unused parameters need not be named, as in `void print(int a, int)`.

## `__func__` (¶7–¶8)

```cpp run ok
#include <cstdio>
struct S {
  S() : s(__func__) { }        // OK: the ctor-initializer is part of the function body
  const char* s;
};
template<class T> void tf() { std::puts(__func__); }
int main() {
  std::puts(__func__);         // Clang/GCC: "main"
  std::puts(S{}.s);            // Clang/GCC: "S"
  tf<int>();                   // Clang/GCC: "tf", without template arguments
  [] { std::puts(__func__); }();   // Clang/GCC: "operator()"
  std::printf("%s\n", __PRETTY_FUNCTION__);   // extension: "int main()"
}
```

¶7 A **function-local predefined variable** is a variable with static storage duration implicitly defined in a function parameter scope.

¶8 `__func__` is such a variable, as if defined as

```cpp
static const char __func__[] = "function-name";
```

where *function-name* is an implementation-defined string. Whether it has an address distinct from other objects in the program is unspecified; the implementation may merge it with string literals of the same contents. A footnote explains that implementations can provide other predefined variables with reserved names, such as GCC/Clang's `__PRETTY_FUNCTION__` and MSVC's `__FUNCSIG__`; the string of a predefined variable that is not odr-used need not appear in the program image.

Example 2 in the standard points out that `void f(const char* s = __func__);` is ill-formed: `__func__` is only available inside a function definition, and the name doesn't exist in a default argument. Clang 23 only gives a `-Wpredefined-identifier-outside-function` warning for this, and the warning satisfies the diagnostic requirement.

!!! tip "`std::source_location`"
    C++20's `std::source_location::current().function_name()` also gives the function name (likewise implementation-defined), and when used as a default argument it gives the caller's location ([[support.srcloc]]), making it better than `__func__` for logging.

## Explicitly-defaulted functions ([dcl.fct.def.default])

### Which functions can be defaulted (¶1)

¶1 A definition whose function body is `= default;` is an **explicitly-defaulted** ([[g:explicitly-defaulted|explicitly-defaulted]]) definition. An explicitly-defaulted function must:

- ¶1.1 be a special member function ([[special]]: default constructor, copy or move constructor, copy or move assignment operator, destructor), a comparison operator function ([[class.compare.default]]), or a postfix increment or decrement operator function ([[over.inc.default]]);
- ¶1.2 have no default arguments.

Defaulting postfix `++`/`--` is a new rule after C++23: `C operator++(int) = default;` means copy `*this`, then call prefix `++`, and return the copy. Clang 23 doesn't support it yet and reports only special member functions and comparison operators may be defaulted.

### How the defaulted version may differ from the implicit one (¶2)

```cpp error
struct S {
  S(int a = 0) = default;               // error: has a default argument
  void operator=(const S&) = default;   // error: the return type should be S&
  ~S() noexcept(false) = default;       // OK: the exception specification may differ
private:
  int i;
  S(S&);                                // OK: private copy constructor
};
S::S(S&) = default;                     // OK: defines the copy constructor
```

¶2 Let F1 be an explicitly-defaulted special member function and F2 the corresponding function the class would have implicitly declared. F1 and F2 can't differ, except in the following ways:

- ¶2.1 if F1 is an assignment operator, it may have a `&` ref-qualifier;
- ¶2.2 if F2 is an assignment operator, F1 may instead have an explicit object parameter of type `C&`: `C& operator=(this C&, const C&) = default;`;
- ¶2.3 the exception specifications may differ;
- ¶2.4 if F2 has a parameter of type `const C&`, the corresponding parameter of F1 may be `C&`;
- ¶2.5 if F2 has a parameter of type `C&` (some member or base can only be copied from a non-const lvalue), F1 may use `const C&`. In that case, if F1 is defaulted on its first declaration, it is defined as deleted; otherwise the program is ill-formed.

```cpp error
struct M { M(M&); };                     // can only be copied from a non-const lvalue
struct H  { M m; H(const H&) = default; };   // ¶2.5: defaulted on first declaration, defined as deleted
struct H2 { M m; H2(const H2&); };
H2::H2(const H2&) = default;             // error: ¶2.5, not the first declaration
```

The example in ¶4 shows the consequence of ¶2.3: if the move constructor of member `T` may throw while `U(U&&) noexcept = default;`, then when `T`'s move constructor really throws, `std::terminate` is called per the usual semantics of noexcept functions.

!!! warning "Tightening after C++26 {{c++29}}"
    [[diff.cpp26.dcl]] records a change incompatible with C++26: defaulted assignment operators no longer allow cv-qualifiers or a `&&` ref-qualifier (¶2.1 only allows `&`), and the parameter of a defaulted move assignment operator can't be a cv-qualified `T&&`.

    ```cpp
    struct S { S& operator=(const S&) && = default; };     // now ill-formed; well-formed in C++26
    struct T { T& operator=(const T&) const = default; };  // now ill-formed; well-formed but deleted in C++26
    struct U { U& operator=(const U&&) = default; };       // now ill-formed; well-formed but deleted in C++26
    ```

    The rationale is to remove rarely used and easily misunderstood forms. Clang 23 still accepts these three lines under the C++26 rules and gives implicitly deleted warnings for the last two.

### Implicitly inline and constexpr (¶3)

¶3 A function explicitly defaulted on its first declaration is implicitly `inline` ([[dcl.inline]]), and if it satisfies the constexpr-suitable conditions ([[dcl.constexpr]]), implicitly `constexpr` too. Note 1 points out that other defaulted functions, i.e. those defaulted outside the class, are not implicitly constexpr.

```cpp error
struct C1 { int x; constexpr C1() : x(0) { } C1(const C1&) = default; };
constexpr C1 a;
constexpr C1 b = a;        // OK: a copy constructor defaulted in the class is implicitly constexpr

struct C2 { int x; constexpr C2() : x(0) { } C2(const C2&); };
C2::C2(const C2&) = default;
constexpr C2 c;
constexpr C2 d = c;        // error: a copy constructor defaulted outside the class is not constexpr
```

### User-provided, and when the definition happens (¶5–¶6)

¶5 Explicitly-defaulted functions and implicitly-declared functions are collectively called **defaulted functions**. The implementation provides implicit definitions for them ([[class.ctor]], [[class.dtor]], [[class.copy.ctor]], [[class.copy.assign]]), some of which are defined as deleted:

- a defaulted prospective destructor (since C++20 a class can have several constrained candidate destructors) that doesn't end up being the destructor is defined as deleted;
- a defaulted special member function that is neither a prospective destructor nor an eligible ([[special]]) special member function is defined as deleted.

A function is **user-provided** ([[g:user-provided|user-provided]]) if it is user-declared and not explicitly defaulted or deleted on its first declaration:

| Form | User-declared | User-provided | Can be trivial |
|---|---|---|---|
| Not written | No | No | Yes |
| `S() = default;` in the class | Yes | No | Yes |
| `S();` in the class, `S::S() = default;` outside | Yes | Yes | No |
| `S() = delete;` in the class | Yes | No | N/A |
| `S() { }` in the class | Yes | Yes | No |

A user-provided explicitly-defaulted function (defaulted after its first declaration) is implicitly defined at the point where it is defaulted; if it would be defined as deleted, the program is ill-formed. Note 2 points out that this form serves both efficiency and a stable binary interface: the function has a real external definition that can later be replaced by a hand-written implementation without changing the header.

A non-user-provided defaulted function (implicitly declared, or defaulted in the class) that isn't defined as deleted is implicitly defined only when it is odr-used or needed for constant evaluation ([[expr.const.defns]]). Note 3 points out that such an implicit definition binds no names.

Example 2 in ¶6 shows the difference between the two kinds of defaulting:

```cpp run ok
#include <type_traits>
struct trivial {
  trivial() = default;                          // defaulted on first declaration: not user-provided
  trivial(const trivial&) = default;
  trivial(trivial&&) = default;
  trivial& operator=(const trivial&) = default;
  trivial& operator=(trivial&&) = default;
  ~trivial() = default;
};
struct nontrivial1 { nontrivial1(); };
nontrivial1::nontrivial1() = default;           // not the first declaration: user-provided

static_assert(std::is_trivially_default_constructible_v<trivial>);
static_assert(!std::is_trivially_default_constructible_v<nontrivial1>);
static_assert(std::is_trivially_copyable_v<trivial>);
int main() { }
```

Whether a function is user-provided affects three things: triviality ([[class.default.ctor]] etc.); whether value-initialization zero-initializes first ([[dcl.init]]: without a user-provided default constructor, value-initialization zeroes the object first); and whether a const object can omit its initializer ([[g:const-default-constructible]]).

```cpp error
struct A { int x; A() = default; };
struct B { int x; B(); };
B::B() = default;

const A ca;   // error: A has no user-provided default constructor, and x has no default member initializer
const B cb;   // OK: B has a user-provided default constructor; cb.x has an erroneous value
```

## Deleted definitions ([dcl.fct.def.delete])

```cpp error
void g(int) = delete("use g(long) to make the width explicit");   // C++26
void g(long) { }

void use() {
  g(1L);                       // OK
  g(1);                        // error: selects the deleted g(int)
  using R = decltype(g(1));    // error: same in an unevaluated operand
}
```

Clang 23's diagnostic for `g(1)` is call to deleted function 'g': use g(long) to make the width explicit.

¶1 A definition whose function body is `= delete;` or `= delete("...");`, as well as an explicitly-defaulted definition that is defined as deleted, is a **deleted definition** of the function. A function with a deleted definition, or one implicitly defined as deleted, is a **deleted function** ([[g:deleted-function|deleted function]]).

### Designating a deleted function is ill-formed (¶2)

!!! std
    A construct that designates a deleted function implicitly or explicitly, other than to declare it or to appear as the operand of a *reflect-expression*, is ill-formed.

¶2 Any construct that designates a deleted function implicitly or explicitly, other than declaring it or being the operand of the reflection operator `^^`, is ill-formed. Note 1 elaborates:

- Designating includes calling it implicitly or explicitly and forming a pointer or pointer to member to the function.
- It is ill-formed even in an expression that is not potentially evaluated, such as `sizeof(f(1))` or `decltype(f(1))`. This differs from a function that is declared but not defined, which is fine as long as it isn't odr-used.
- For an overload set, only the function selected by overload resolution counts as designated.
- The implicit odr-use of a virtual function doesn't by itself designate it, so a virtual function can be deleted as long as it is never called.

*Recommended practice*: when an *unevaluated-string* is provided, the diagnostic should include its text. A note explains that it can be used to explain why the function is deleted or to suggest an alternative.

Deleted functions take part in overload resolution precisely so that selecting one is an error. If they didn't, `g(1)` would silently select `g(long)`, which is exactly what the author wanted to prevent. The old C++03 trick was to declare the function private and not define it, which gives an access error, and when called from the class's own members, the error is delayed until link time; `= delete` gives an accurate error at compile time.

### Typical uses (¶3)

The standard gives three examples:

```cpp error
#include <cstddef>
struct onlydouble {                    // 1. accepts only double
  onlydouble() = delete;               // OK, but redundant
  template<class T> onlydouble(T) = delete;
  onlydouble(double);
};
onlydouble b(1);                       // error: selects the deleted onlydouble<int>

struct sometype {                      // 2. can't be created with new
  void* operator new(std::size_t) = delete;
  void* operator new[](std::size_t) = delete;
};
sometype* p = new sometype;            // error: deleted class operator new
sometype* q = new sometype[3];         // error: deleted class operator new[]

struct moveonly {                      // 3. move-only
  moveonly() = default;
  moveonly(const moveonly&) = delete;
  moveonly(moveonly&&) = default;
  moveonly& operator=(const moveonly&) = delete;
  moveonly& operator=(moveonly&&) = default;
  ~moveonly() = default;
};
moveonly* mp;
moveonly mq(*mp);                      // error: deleted copy constructor
```

`onlydouble() = delete;` is redundant because the class already declares another constructor, so the default constructor wouldn't be implicitly declared anyway. Other common uses are `void f(std::nullptr_t) = delete;` (forbidding passing `nullptr`) and `void ref(const T&&) = delete;` to forbid binding temporaries, which is what the standard library's `std::ref` does.

### A deleted definition must be the first declaration (¶4)

<div class="compare" markdown="1">

```cpp ok
template<class T> void process(T) { }
template<> void process<bool>(bool)
    = delete;  // first declaration of the specialization
int main() { process(1); }
```

```cpp error
struct sometype { sometype(); };
sometype::sometype() = delete;
  // error: not the first declaration
```

</div>

¶4 A deleted function is implicitly `inline` ([[dcl.inline]]); Note 2 points out that the ODR applies to deleted definitions too, so they must agree across translation units.

A deleted definition must be the first declaration of the function; for an explicit specialization of a function template, it must be the first declaration of that specialization. This way, every place that can see the function knows it is deleted. If declaring first and deleting later were allowed, the compiler would consider the function usable at call sites before the deleted definition, and the rule that designating it is ill-formed couldn't be enforced consistently. The relaxation for explicit specializations makes it possible to keep the primary template usable and delete just one specialization.

The implicitly declared global allocation and deallocation functions ([[basic.stc.dynamic]]) can't be defined as deleted.

## Replaceable functions ([dcl.fct.def.replace])

```cpp run ok
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocations = 0;

void* operator new(std::size_t n) {     // replacement function
  ++allocations;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  delete new int(1);
  std::printf("allocations: %d\n", allocations);   // at least 1
}
```

¶1 Certain functions whose definitions are supplied by the implementation are **replaceable** ([[g:replaceable-function|replaceable]]). A program can provide a definition with the same signature, called a **replacement function** ([[g:replacement-function|replacement function]]), and the program then uses it instead of the implementation's default version. Replacement happens before program startup ([[basic.def.odr]], [[basic.start]]); it is not a run-time switch. The declaration of a replacement function must:

- ¶1.1 not be `inline`;
- ¶1.2 be attached to the global module; replacement can't be done in a named module;
- ¶1.3 have C++ language linkage;
- ¶1.4 have the same return type as the replaceable function;
- ¶1.5 if the function is declared in a standard library header, be a valid redeclaration of that declaration.

Violating any of these is {{ifndr}}: ill-formed, but the compiler isn't required to diagnose it.

Note 1 points out that the ODR applies to the program-supplied replacement definition, so there can be only one in the whole program; the implementation-supplied definition is an unnamed function with no linkage, so the two don't conflict under the ODR.

It can't be `inline` because a replacement function must take over all calls before program startup, including those inside the standard library and in other translation units; an `inline` function can have a definition in each of several translation units and may be inlined into call sites, which conflicts with the meaning of whole-program replacement.

The list of replaceable functions is scattered; the main ones are the various forms of global `operator new`/`operator delete` ([[replacement.functions]], [[new.delete]]); C++26's contract-violation handler `::handle_contract_violation` is also replaceable ([[basic.contract.handler]]).

## Implementation notes

!!! impl
    - A function defaulted on its first declaration that is trivial generates no code: copying is a bytewise copy, and construction does nothing. A function defaulted outside the class is a real external function, with call overhead even if its body is empty (unless LTO is on), and the type loses triviality. This affects the ABI: in the Itanium C++ ABI, a type with a non-trivial copy constructor or destructor can't be passed in registers, only indirectly through memory.
    - Deleted functions generate no code and no symbols.
    - At the linking level, replacing `operator new` usually amounts to the definition in the user's object file taking precedence over the one in the runtime library; when the runtime library is a shared library, it also relies on the dynamic linker's symbol interposition so that calls inside the library go to the replacement too.

## History

!!! history
    - C++98: function definitions and function-try-blocks; the rules for replacing global `operator new`/`delete` were in the library clauses.
    - C++11: `= default` and `= delete` ([[N2346]]); `__func__` adopted from C99.
    - C++20: comparison operators `==` and `<=>` can be defaulted ([[class.compare.default]]); prospective destructors introduced.
    - C++23: defaulted assignment operators can use an explicit object parameter (¶2.2).
    - C++26: `= delete("reason")` ([[P2573R2]]); deleted functions can be the operand of `^^`; the new [dcl.fct.def.replace] describes replaceable functions uniformly in the core language.
    - After C++26: defaulted assignment operators no longer allow cv and `&&` qualifiers ([[diff.cpp26.dcl]]); postfix `++`/`--` can be defaulted.

## Common misconceptions

!!! pitfall "`= default` outside the class is the same as inside"
    With `struct S { S(); }; S::S() = default;`, `S` is no longer trivially default constructible. That's fine if you only want to move the implementation out of the header; when you need triviality (e.g. for `std::is_trivially_*` optimizations or C interoperability), default it in the class.

!!! pitfall "Writing `= default` means the function exists"
    If a member isn't copyable, `S(const S&) = default;` in the class is defined as deleted. There's no error at the declaration, only at use. Clang's `-Wdefaulted-function-deleted` flags this.

!!! pitfall "You can probe a deleted function's return type with `decltype`"
    Designating a deleted function is ill-formed even when unevaluated. In substitution during template argument deduction this shows up as substitution failure, so `requires { f(x); }` can detect that `f(x)` would select a deleted function.

!!! pitfall "You can delete a function later in the .cpp file"
    A deleted definition must be the first declaration: you can't declare `void f(int);` in a header and then write `void f(int) = delete;` in a `.cpp` file.

## Questions

!!! question "Question 1"
    For which of these types is `std::is_trivially_copyable_v` true?
    ```cpp
    struct A { A(const A&) = default; };
    struct B { B(const B&); };  B::B(const B&) = default;
    struct C { C(const C&) = delete; };
    struct D { D(const D&) = default; int& r; };
    ```

<details markdown="1">
<summary>Answer</summary>

- `A`: true. The copy constructor is defaulted on its first declaration and is trivial.
- `B`: false. Defaulted outside the class, so it is user-provided and not trivial.
- `C`: true. Trivially copyable requires at least one eligible copy or move operation, with all eligible copy and move operations and the destructor trivial ([[class.prop]]). The deleted copy constructor is not eligible ([[special]]); because a copy constructor is user-declared, the move operations aren't implicitly declared; but the copy assignment operator is still implicitly declared as defaulted and trivial, so there is one eligible trivial operation. A type that can't be copy-constructed is trivially copyable, a very counterintuitive conclusion.
- `D`: true. The copy constructor is trivial; copy assignment is defined as deleted because of the reference member and is not eligible; the move operations aren't declared. There are still a trivial, eligible copy constructor and destructor.

Clang 23's results agree with the above.
</details>

!!! question "Question 2"
    Why does `template<class T> onlydouble(T) = delete;` block `onlydouble x(1.0f);`?

<details markdown="1">
<summary>Answer</summary>

In overload resolution, the template specialization `onlydouble<float>(float)` is an exact match, while `onlydouble(double)` needs a floating-point promotion; an exact match is better ([[over.ics.rank]]), so the deleted template specialization is selected and the call is ill-formed. Only when the argument is exactly `double` are both exact matches, and then the rule preferring non-templates selects `onlydouble(double)`.
</details>
