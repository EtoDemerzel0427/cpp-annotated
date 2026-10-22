---
title: C++ and C
summary: Where valid C code fails to compile as C++, where it compiles but changes meaning, and the design rationale behind each difference; with the results of compiling with Clang 23 as C17 and as C++2c.
updated: 2026-10-19
---

!!! tldr
    - This subclause lists 39 places where valid C code is ill-formed, undefined or different in meaning in C++; you will meet them when writing headers shared by C and C++ or migrating a C project to C++.
    - Most of the differences come from C++'s stricter type checking: `void*` does not convert implicitly to other object pointers, enumerations do not freely interchange with integers, and string literals are `const`.
    - Another group comes from scope rules: a `struct` is a scope in C++, class names and ordinary names share one namespace, and an inner `struct x` hides an outer variable `x`.
    - Changes in meaning with no compiler error: `sizeof('x')`, `sizeof(0, arr)`, an inner class name hiding an outer object, and internal linkage of file-scope `const`. `&*p` and `&a[N]` are well-defined in C but UB in C++.
    - Clang only warns for several of these (`char* p = "abc"`, `static` on a type declaration, calling `main` recursively, C-style designated initializers); `-pedantic-errors` turns them into errors.

The annex does not name any particular C version; the entries are about C's current rules. Compared with the other subclauses, entries here have two extra items: the difficulty of converting and how widely the construct is used. They are collected in the table at the end of the page.

The tests below use Clang 23.1.3 to compile the same source file as `clang -x c -std=c17` and as `clang++ -x c++ -std=c++2c`.

## Lexical conventions {#diff.lex}

### New keywords

```cpp error
int class = 1, new = 2, this = 3;   // valid C
```

¶1 C++ adds keywords such as `class`, `new`, `delete`, `this`, `template`, `namespace`, `private`, `virtual`, `operator`, `friend`, `try`, `catch` and `throw` ([[lex.key]]). A C program that uses them as identifiers is not a valid C++ program. `new`, `class` and `this` as variable or struct member names are quite common in C code.

### Character literals have type `char`

```cpp
int function(int i);
int function(char c);
int n = function('x');           // calls function(char)
int sz = sizeof('x');            // C: sizeof(int); C++: 1
```

¶2 A character literal `'x'` has type `int` in C and `char` in C++ ([[lex.ccon]]). This makes overload resolution more sensible: `function('x')` should match `function(char)`. The cost is that a C program relying on `sizeof('x') == sizeof(int)` gives a different result in C++, and the compiler says nothing.

### Concatenated string literals cannot have conflicting encoding prefixes

¶3 Adjacent string literals with different encoding prefixes, such as `L"a" U"b"`, are ill-formed in C++ ([[lex.string]]). In C, whether this is supported is implementation-defined; it is a non-portable feature. See also [[diff.cpp20]].

### String literals are `const`

```cpp error
char* p = "abc";          // valid C; ill-formed in C++
void f(char*);
void g() {
  f((char*)"def");        // OK: the fix the annex gives
}
```

¶4 In C++, an ordinary string literal has type array of `const char`, not array of `char` as in C. Wide, UTF-8, UTF-16 and UTF-32 string literals are likewise arrays of `const wchar_t`, `const char8_t`, `const char16_t` and `const char32_t` ([[lex.string]]). The rationale is to avoid calling an overloaded function that might modify its argument. Modifying a string literal is UB in C too; the type system just does not prevent it.

In C++ mode Clang only warns `ISO C++11 does not allow conversion from string literal to 'char *'` for the first line; it is an error only with `-pedantic-errors`. The fix the annex suggests is a cast; the better approach is to make the pointer `const char*`.

## Basics {#diff.basic}

### No tentative definitions

```cpp error
int i;
int i;   // valid C; a redefinition in C++
```

¶1 C allows a file-scope object declaration without an initializer and without `extern` to appear several times in the same translation unit, finally merging into one definition; this is a tentative definition ([[g:tentative-definition]]). In C++ each such declaration is a definition ([[basic.def]]), and the second one is a redefinition.

One consequence: using only C's initialization syntax, you cannot define a set of mutually referencing file-local static objects in C++.

```cpp error
struct X { int i; struct X* next; };
static struct X a;               // C: tentative definition; C++: definition
static struct X b = { 0, &a };
static struct X a = { 1, &b };   // C++: redefinition
```

The rationale is to avoid having different initialization rules for built-in types and user-defined types. In C++, one of the objects in such a set has to be initialized some other way, such as through a function call.

### A `struct` is a scope

```cpp error
struct X {
  struct Y { int a; } b;
};
struct Y c;   // valid C; in C++ write X::Y c;
```

¶2 In C++ a `struct` is a class, and class scope is central to C++ ([[basic.scope]]). In C, a struct tag defined in a nested position belongs to the enclosing scope. In C++, `Y` is `X::Y`, and the `struct Y` on the last line declares a new, incomplete global type; Clang reports `variable has incomplete type 'struct Y'`. You only run into this when referring to a nested struct, enumeration or enumerator name from outside; see nested class names in the classes section below.

### File-scope `const` objects have internal linkage

```cpp title="a.c"
const int limit = 10;
```

```cpp title="b.c"
extern const int limit;
int main(void) { return limit; }
```

¶3 A name at file scope that is explicitly declared `const` and not explicitly declared `extern` has internal linkage in C++ and external linkage in C ([[basic.link]], see also [[dcl.type]]). Compiled and linked as C, the two files above produce a program that returns 10; compiled as C++, the `limit` in `a.c` is invisible to other translation units, and linking fails with an undefined symbol.

C++ does this because `const` objects can be used as values at compile time: programmers are encouraged to give every `const` object an initializer and put it in headers included by multiple translation units. When you need external linkage, add `extern` at the definition: `extern const int limit = 10;`. Since C++17, the better form in a header is `inline constexpr int limit = 10;`.

### `main` cannot be called recursively or have its address taken

¶4 In C++, `main` may need special handling, for example the implementation inserting code at its start to initialize static objects, so a program may not call it recursively or take its address ([[basic.start.main]]). The fix is simple: introduce an intermediary function, such as `mymain(argc, argv)`. Clang does not diagnose this by default; only with `-pedantic` does it warn `referring to 'main' within an expression is a Clang extension` at each use.

### C's compatible types

¶5 C allows mixing compatible types in many places, and C++ does not ([[basic.types]]). For example, in C an enumeration type is compatible with its underlying integer type; in C++ an enumeration is a distinct type from its underlying type. Stricter type checking is essential for C++. The annex notes that typesafe linkage, which puts parameter types into mangled names, finds many but not all such problems; some cases are also allowed in C++ by the layout-compatibility rules.

## Expressions {#diff.expr}

### `void*` does not convert implicitly to an object pointer

```cpp error
char a[10];
void* b = a;
void foo() {
  char* c = b;   // valid C; ill-formed in C++
}
```

¶1 C++ tries harder than C to enforce type safety at compile time: a conversion from `void*` to an object pointer must be written explicitly ([[conv.ptr]]). The compiler diagnoses every such conversion, and the fix is a cast, `char* c = (char*)b;`. The most common place is `int* p = malloc(n * sizeof *p);`.

### Enumerations cannot be mixed with other enumerations or floating-point in arithmetic

```cpp error
enum E1 { e };
enum E2 { f };
int b = e <= 3.7;     // valid C; ill-formed in C++
int k = f - e;        // valid C; ill-formed in C++
int x = 1 ? e : f;    // valid C; ill-formed in C++
```

¶2 When one operand is an enumeration and the other is a different enumeration or a floating-point type, the usual arithmetic conversions are ill-formed in C++ ([[expr.arith.conv]]), to strengthen type safety. These forms were deprecated since C++20 and became ill-formed only in C++26 ([[diff.cpp23]]). Doing the integral promotion first with a cast or unary `+` restores the original behavior: `(int)e <= 3.7`, `+f - e`.

### Enumerations are treated differently in the usual arithmetic conversions

```cpp
typedef enum { E0 } E;   // in C the underlying type of E may be unsigned int
static_assert(((E)E0 - 1 < 0) == (E0 - 1 < 0), "Must pass for C++");
```

¶3 For an enumeration without a fixed underlying type, C converts its value to the enumeration's underlying type in the usual arithmetic conversions, and the underlying type is chosen by the implementation and may be `unsigned int`. C++ instead applies integral promotion based on the enumeration's range of values ([[conv.prom]], [[dcl.enum]]), which usually gives `int`.

In the example above, `E0` has type `int` in C and `(E)E0` has type `E`. When the underlying type is `unsigned int`, `(E)E0 - 1` is a large unsigned number and the assertion fails. In C++ both sides are promoted to `int`, and the assertion always holds. This is exactly the problem C++ wants to avoid: replacing an enumerator with the same enumerator converted to the enumeration type should not change the result of an expression. With Clang 23, this assertion does fail when compiled as C17 and passes when compiled as C++.

### `bool` cannot be decremented

¶4 Applying `--` to a `bool` lvalue is ill-formed in C++ ([[expr.post.incr]], [[expr.pre.incr]]), and valid in C with `bool` from `<stdbool.h>` or `_Bool`. The semantics of this operation are surprising. Since C++17, `++` is no longer allowed either ([[diff.cpp14]]).

### `&*p` and `&a[N]`

```cpp ub
void f() {
  char* p = nullptr;
  char* p2 = &*p;     // C: well-defined; C++: UB
  char* p3 = &p[0];   // C: well-defined; C++: UB
  int a[5];
  int* q = &a[5];     // C: well-defined; C++: UB
}
```

¶5 The C standard explicitly says that `&*E` is equivalent to `E` and `&E[i]` to `E + i`, with the `*` and `[]` effectively not evaluated, so writing this on a null or past-the-end pointer is well-defined. C++ treats lvalues uniformly and has no such special rule: `*p` first forms an lvalue, and if `p` does not point to an object, that step is already UB ([[expr.unary.op]]).

The fix is to rewrite it as pointer arithmetic, such as `a + 5` or `p + 0`, adding a null check where needed. `&a[N]` as a way to write a past-the-end pointer is not uncommon in C-style code.

### Types can only be defined in declarations

```cpp error
void* p;
void f() { p = (void*)(struct x { int i; }*)0; }
```

¶6 C allows a new type to be defined in a `sizeof` expression or a cast expression; the example above defines `struct x`. In C++, types can only be defined in declarations ([[expr.sizeof]], [[expr.cast]]), so where a definition is in the source is clearer. Clang reports `'x' cannot be defined in a type specifier`.

### Arrays cannot be compared directly

<div class="compare" markdown="1">

```cpp error
int arr1[5];
int arr2[5];
int same = arr1 == arr2;
// valid C; ill-formed in C++
```

```cpp ok
int arr1[5];
int arr2[5];
int idem = arr1 == +arr2;
// valid in C++; a constraint violation in C
```

</div>

¶7 C allows comparing two arrays directly; what is compared is the decayed addresses, not the contents, which is easy to misunderstand. Since C++26 such comparisons are ill-formed ([[expr.rel]], [[expr.eq]], see also [[diff.cpp23]]). Compiled as C17, Clang only warns that the comparison is always `false`; compiled as C++2c, it reports `comparison between two arrays is ill-formed in C++26`.

The annex suggests converting either array to a pointer with unary `+`. But C's unary `+` does not accept pointers, so code shared by C and C++ should write `&arr1[0] == &arr2[0]`.

### Conditional, assignment and comma expressions can yield lvalues

```cpp ok
char arr[100];
int s = sizeof(0, arr);   // C++: 100; C: sizeof(char*)
```

¶8 In C++ the result of a conditional expression, an assignment expression or a comma expression can be an lvalue; in C they are always rvalues ([[expr.cond]], [[expr.assign]], [[expr.comma]]). C++ places more emphasis on lvalues; function calls can produce lvalues too, for example. In the example above, in C++ the result of the comma expression is the array lvalue itself and `sizeof` gives 100; in C the result has gone through the array-to-pointer conversion. Compiling as C, Clang gives a `-Wsizeof-array-decay` warning; compiling as C++, there is no diagnostic. C code that relies on this needs an explicit conversion to the appropriate rvalue.

## Statements {#diff.stat}

### Declarations with initialization cannot be jumped over

```cpp error
void f(int n) {
  goto L;
  int x = n;   // valid C; in C++ the initialization is jumped over
L:
  (void)x;
}
```

¶1 In C++, jumping past a declaration with explicit or implicit initialization is ill-formed, unless the whole block that is not entered is jumped over ([[stmt.switch]], [[stmt.goto]]). Constructors in initializers may allocate resources that must be released when leaving the block; allowing initialization to be skipped would require complicated run-time checks, and many operations on uninitialized objects are UB. With this compile-time rule, a variable that has an initializer is guaranteed to have been initialized whenever it is in scope.

Clang reports `cannot jump from this goto statement to its label`. A `case` label of a `switch` jumping past an initialization is the same; wrap the declaration in that `case` in a pair of braces.

### A function declared with a return type must return a value

¶2 Returning without a value from a function declared with a return type is invalid in C++ ([[stmt.return]]). Caller and callee may use elaborate mechanisms for returning class objects, and having some paths return without a value would complicate implementations considerably. Besides, promising a return value and not returning one has always been considered questionable practice, tolerated only because very early C did not distinguish `void` and `int` return types.

There are two cases here. An explicit `return;` is ill-formed in C++ and must be diagnosed; Clang treats it as an error under C17 as well (`-Wreturn-mismatch`). Flowing off the end of a non-`void` function is run-time UB ([[stmt.return#4]]), and compilers usually only give a `-Wreturn-type` warning. The fix is to add a suitable return value.

## Declarations {#diff.dcl}

### Variables cannot be declared with type `void`

¶1 In C++, no variable declaration can have type cv `void`. C allows it as long as it is not a definition, for example `extern void x;` ([[dcl.pre]]). This is stricter type checking.

### Storage class specifiers apply only to objects and functions

```cpp error
static struct S {   // valid C; ill-formed in C++
  int i;
};
```

¶2 In C++, `static` and `extern` can only be applied to names of objects and functions ([[dcl.stc]]); in C they are ignored on type declarations. Storage class specifiers mean nothing on a type, and since C++ class members can be declared `static`, writing it on a type declaration is confusing. Clang only warns `'static' is not permitted on a declaration of a type` in C++ and does not reject it.

### `register` is not a storage class specifier

¶3 `register` has no effect in C++, and since C++17 it is no longer a storage class specifier ([[dcl.stc]], see also [[diff.cpp14]]). It is common in old C code; just delete it. In C++17 and later modes Clang reports `ISO C++17 does not allow 'register' storage class specifier`.

### A typedef name cannot be the same as a class name in the same scope

```cpp error
typedef struct name1 { int a; } name1;   // valid in both C and C++
struct name { int a; };
typedef int name;                        // valid C; ill-formed in C++
```

¶4 In C, typedef names and struct tags are in different name spaces and can be the same. In C++, a typedef name must differ from any class name in the same scope, unless it is a synonym for that very class ([[dcl.typedef]]). The reason is that C++ does not require the `class`, `struct` or `union` prefix when declaring objects or in casts: given `class name {…};`, you can write `name i;` directly. One of the two types has to be renamed.

### `const` objects must be initialized

¶5 `const int ci;` is valid in C and ill-formed in C++ ([[dcl.type]], see also [[basic.link]]). A `const` object cannot be assigned to, so without initialization it cannot hold a useful value. Clang reports `default initialization of an object of const type 'const int'`.

### `auto` cannot be used as a storage class specifier

¶6 C's `auto int x;` is ill-formed in C++ ([[dcl.spec.auto]]). C++ uses `auto` to deduce a variable's type from its initializer, and allowing it as a storage class specifier at the same time would produce unwanted interpretations in some contexts. Clang only gives a `-Wauto-storage-class` warning for it.

### An empty parameter list means no arguments

```cpp
int f();   // C++: equivalent to int f(void)
           // C17 and earlier: number and types of arguments unknown
```

¶7 In C++, an empty parameter list means the function takes no arguments ([[dcl.fct]]), which prevents calling a function with the wrong number or types of arguments. C long ago marked declarations without prototypes as obsolescent, and C23 also changed it to mean the same as in C++. When converting, complete C's incomplete declarations into prototypes; if different calls to the same unprototyped function pass different numbers or types of arguments, the program needs further changes.

### Types cannot be defined in return or parameter types

```cpp error
void f( struct S { int a; } arg ) {}   // valid C; ill-formed in C++
enum E { A, B, C } g() {}              // valid C; ill-formed in C++
```

¶8 In C++, types cannot be defined in return types or parameter types ([[dcl.fct]], see also [[expr.sizeof]]). When comparing types across translation units, C++ relies on name equivalence and C on structural equivalence. As for parameter types: a type defined in a parameter list is in the function's scope, so in C++ the only legal calls would come from within the function itself. Type definitions must move to file scope or to headers.

### No old-style function definitions

```cpp error
int f2(a, b) int a; int b; { return a + b; }   // K&R style
```

¶9 C++'s function definition syntax does not include C's old-style (K&R) definitions ([[dcl.fct.def]]), because prototypes are essential for type safety. This form has long been obsolescent in C: Clang warns under C17 that it is not supported in C23, and under C++ reports a string of syntax errors.

### Designated initializers are restricted

```cpp
struct A { int x, y; };
struct B { struct A a; };
struct A a = {.y = 1, .x = 2};  // valid C; ill-formed in C++: out of order
int arr[3] = {[1] = 5};         // valid C; ill-formed in C++: array designator
struct B b = {.a.x = 0};        // valid C; ill-formed in C++: nested designator
struct A c = {.x = 1, 2};       // valid C; ill-formed in C++: mixed
```

¶10 C++'s designated initialization is more restricted than C's ([[dcl.init.aggr]]): designators for non-static data members must appear in declaration order; array element designators and nested designators are not supported; and designated and non-designated initializers cannot be mixed in the same initializer list.

Each has a reason. In C++ members are destroyed in the reverse order of construction, and the elements of an initializer list are evaluated in the order written, so member initializers must be given in order. The array designator `[1]` conflicts with lambda expression syntax. Nested designators are seldom used.

Clang accepts all four forms in C++ as extensions, with a `-Wreorder-init-list` warning and three `-Wc99-designator` warnings respectively. GCC reports out-of-order designators as errors. Portable shared code should follow declaration order.

### A character array initialized from a string must have room for `'\0'`

```cpp error
char array[4] = "abcd";   // valid C (the terminating '\0' is not stored); ill-formed in C++
```

¶11 In C++, when a character array is initialized from a string, the number of characters in the string (including the terminating `'\0'`) must not exceed the number of array elements ([[dcl.init.string]]). C allows the array to be exactly one too small for the terminating `'\0'`, and handing an array without a terminating zero to the standard string functions can have serious consequences. Declare the array one element larger; when you really need a byte array without a terminating zero, write `{'a', 'b', 'c', 'd'}`.

### An enumeration object can only be assigned values of the same enumeration type

```cpp error
enum color { red, blue, green };
enum color c = 1;   // valid C; ill-formed in C++
```

¶12 In C an object of enumeration type can be assigned a value of any integer type; in C++ only values of the same enumeration type ([[dcl.enum]]), as part of C++'s type safety. An explicit conversion fixes it; this form is common in C code.

### The type of an enumerator is its enumeration

```cpp error
enum e { A };
void f() {
  auto x = A;
  int* p = &x;   // valid C23; in C++ x has type enum e
}
```

¶13 In C++ the type of an enumerator is its enumeration type; in C it is some integer type ([[dcl.enum]]). In C++ an enumeration is a distinct type. Compiling the example as C23, `x` has type `int`; compiling it as C++, Clang reports `cannot initialize a variable of type 'int *' with an rvalue of type 'e *'`.

### Alignment specifiers are attribute specifiers

```cpp
#include <stdalign.h>
unsigned alignas(8) int x;   // valid C; ill-formed in C++
unsigned int y alignas(8);   // valid C++; ill-formed in C
```

¶14 In C++ an alignment specifier is an attribute specifier, and its position is governed by attribute syntax; in C it is a declaration specifier and can be mixed with the other specifiers ([[dcl.align]]). C++ requires the position of an alignment specifier to be unambiguous. The form that works in both C and C++ puts it at the very start of the declaration: `alignas(8) unsigned int x;`.

## Classes {#diff.class}

### An inner class name hides an outer object

```cpp run title="hide.c" ok
#include <stdio.h>
int x[99];
int main(void) {
  struct x { int a; };
  printf("%zu\n", sizeof(x));   // C: size of the array; C++: size of the struct
}
```

¶1 In C++, a class declaration introduces the class name into the scope where it is declared and hides any object, function or other declaration of the same name in an enclosing scope ([[class.name]], see also [[dcl.typedef]]). In C, a struct tag in an inner scope never hides an object or function name in an outer scope. The same file prints `396` compiled as C and `4` compiled as C++, with no diagnostic at all.

This is one of the few incompatibilities caused by C++'s name space rules. In C++ a name can be declared both as a type and as a non-type in the same scope; the non-type name then hides the type name, and referring to the type requires `class`, `struct`, `union` or `enum`. These rules let user-defined types be used as much like fundamental types as possible, and the committee judged the benefit to far outweigh this incompatibility. If the hidden name is at global scope, it can be accessed as `::x`; if it is at block scope, either the type or the object has to be renamed.

### Implicit copy operations cannot copy `volatile` lvalues

```cpp error
struct X { int i; };
volatile struct X x1 = {0};
void f() {
  struct X x2 = x1;   // valid C; ill-formed in C++
  struct X x3;
  x3 = x1;            // also ill-formed
}
```

¶2 The parameter of the implicitly declared copy constructor and copy assignment operator is `const X&`, which cannot bind to a `volatile X` lvalue ([[class.copy.ctor]]). The committee discussed alternatives: making the parameter `const volatile X&` would make it hard to generate efficient code for class objects; providing two signatures for the implicit operations could cause ambiguities and complicate the rules that decide the form of these operations from bases and members.

Clang reports `no matching constructor for initialization of 'struct X'` and `no viable overloaded '='`. When you need `volatile` semantics for the copy, declare the constructor or assignment operator yourself; when you don't, `const_cast` can remove the `volatile`.

### Plain `int` bit-fields are signed

¶3 In C, whether `int b : 3;` is signed or unsigned is implementation-defined; in C++ it is signed ([[class.bit]]). Different specializations of the same template must agree on signedness, and for consistency this implementation freedom was removed for non-dependent types as well.

### Nested class names are local to the enclosing class

```cpp error
struct X {
  struct Y { int a; } y;
};
struct Y yy;   // valid C; ill-formed in C++
```

¶4 In C++ the name of a nested class belongs to the enclosing class; in C it belongs to the same scope as the outermost enclosing struct ([[class.nest]]). C++ classes have member functions, which requires classes to establish scopes. Under C's rules a class could only be an incomplete scoping mechanism, and programmers could not maintain locality within a class; a set of C++ scope rules built on C's would be very complicated, and examples involving nested classes or local functions would be hard to predict.

The annex suggests declaring `struct Y;` before the enclosing struct. That works in C, but in C++ a `struct Y { … }` with a class body inside `X` still defines a new member class `X::Y` and does not complete the outer `::Y`, and Clang still reports `variable has incomplete type 'struct Y'`. The fix that works in both languages is to move the definition of `Y` outside `X` and write only `struct Y y;` inside `X`.

### A typedef name cannot be redeclared in a class after being used

```cpp ifndr
typedef int I;
struct S {
  I i;
  int I;   // valid C; IFNDR in C++
};
```

¶5 In C++, once a typedef name has been used in a class definition, it cannot be redeclared in the same class ([[class.member.lookup]]). As classes get complicated, allowing such redefinitions would make it unclear what `I` actually refers to. Per [[class.member.lookup#6]] in the current draft, if looking up `I` in the class gives a different result from looking it up in the complete-class context, the program is ill-formed, no diagnostic required. Clang gives no diagnostic for this code.

## Preprocessing directives {#diff.cpp}

¶1 Whether `__STDC__` is predefined, and its value, are implementation-defined in C++ ([[cpp.predefined]]). C++ is not C, and requiring `__STDC__` to be defined would require the compiler to make an untrue claim. Headers that use `#ifdef __STDC__` to detect standard C may take a different branch in C++. Clang still defines `__STDC__` as 1 in C++ mode; to detect C++, use `__cplusplus`.

## Summary

The table below collects, in the annex's own terms, the difficulty of converting and how widely used each entry is. For changes that can be automated, the compiler points out every location; semantic transformations require understanding the code and rewriting it by hand.

| Entry | Difficulty of converting | How widely used |
|---|---|---|
| [lex] new keywords | syntactic transformation; converting a large collection of related programs takes more work | common |
| [lex] `sizeof('x')` | simple | programs depending on it are probably rare |
| [lex] conflicting encoding prefixes | syntactic transformation | seldom |
| [lex] `const` string literals | syntactic transformation (add a cast) | programs with a legitimate reason to modify literals are probably rare |
| [basic] tentative definitions | semantic transformation | seldom |
| [basic] `struct` scope | semantic transformation | noticed only when referring to nested names from outside, probably rare |
| [basic] internal linkage of `const` | semantic transformation | seldom |
| [basic] calling `main` recursively | trivial | seldom |
| [basic] compatible types | semantic transformation | common |
| [expr] `void*` conversion | can be automated | common |
| [expr] mixed enumeration arithmetic | diagnosed by the compiler | uncommon |
| [expr] arithmetic conversions of enumerations | add explicit casts | rare |
| [expr] `bool` decrement | not given by the annex | not given by the annex |
| [expr] `&*p`, `&a[N]` | syntactic transformation | occasionally |
| [expr] defining types in expressions | syntactic transformation | seldom |
| [expr] array comparison | diagnosed by the compiler | rare |
| [expr] lvalue results | add explicit casts | rare |
| [stmt] jumping past initialization | semantic transformation | seldom |
| [stmt] not returning a value | semantic transformation | seldom |
| [dcl] `void` variables | syntactic transformation | seldom |
| [dcl] `static` on type declarations | syntactic transformation | seldom |
| [dcl] `register` | syntactic transformation | common |
| [dcl] typedef with the same name as a class | semantic transformation | seldom |
| [dcl] uninitialized `const` | semantic transformation | seldom |
| [dcl] `auto` storage class | syntactic transformation | rare |
| [dcl] empty parameter lists | syntactic transformation | common |
| [dcl] defining types in parameter or return types | semantic transformation | seldom |
| [dcl] K&R function definitions | syntactic transformation | common in old programs |
| [dcl] designated initializers | syntactic transformation | out of order is common, the rest seldom |
| [dcl] character array with no room for `'\0'` | semantic transformation | seldom |
| [dcl] assigning integers to enumerations | syntactic transformation | common |
| [dcl] type of enumerators | semantic transformation | seldom |
| [dcl] position of alignment specifiers | syntactic transformation | seldom |
| [class] class name hiding an object | semantic transformation | seldom |
| [class] copying `volatile` objects | semantic transformation | seldom |
| [class] signedness of `int` bit-fields | syntactic transformation | seldom |
| [class] nested class names | semantic transformation | seldom |
| [class] typedef redeclaration | semantic transformation | seldom |
| [cpp] `__STDC__` | semantic transformation | fairly common |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 [diff.iso.general] says that this subclause lists the differences between C++ and C by the chapters of this document, in addition to the differences listed in the preceding subclauses.

</details>
