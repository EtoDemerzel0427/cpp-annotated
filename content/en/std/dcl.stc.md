---
title: Storage class specifiers
summary: "Where static, thread_local, extern and mutable may be used and how they combine; all declarations of an entity must give it the same linkage; why auto and register are no longer storage class specifiers."
updated: 2026-10-19
---

!!! tldr
    - There are four storage class specifiers: `static`, `thread_local`, `extern` and `mutable`. A declaration may contain at most one, except that `thread_local` may appear together with `static` or `extern`.
    - Variables at namespace scope already have static storage duration; there `static` only changes the linkage to internal. In a block, `static` changes the storage duration.
    - A block-scope `thread_local` variable implies `static`: one copy per thread, retained across calls.
    - All declarations of an entity must give it the same linkage: `static` followed by `extern` is fine (internal linkage is inherited), external linkage followed by `static` is an error.
    - `mutable` can only be used on non-static data members that are neither const nor references, and makes them modifiable even inside a const object.

These four specifiers have names that come from C, but only `static` and `thread_local` actually determine storage duration ([[basic.stc]]). `extern` mainly affects linkage and whether a declaration is a definition ([[basic.link]], [[basic.def]]), and `mutable` has nothing to do with storage. This subclause specifies where they can be used and how they combine; most of their semantic effects are given by the subclauses just mentioned.

## Combination rules (¶1)

```cpp run ok
extern thread_local int counter;           // OK: thread_local can be written with extern
thread_local int counter = 0;              // every declaration has thread_local
static struct Point { int x, y; } origin;  // static applies to origin, not to Point
static union { int u_i; float u_f; };      // an anonymous union may have no declarator
int main() { return counter + origin.x + u_i; }
```

¶1 specifies:

1. A specifier sequence contains at most one storage class specifier, except that `thread_local` may appear together with `static` or `extern`.
2. If any declaration of a variable has `thread_local`, all of its declarations must.
3. It can't appear together with `typedef`; type aliases have no storage duration.
4. The declarator list can't be empty, except for an anonymous union at namespace scope. A storage class specifier modifies the declared variable or function; without a declarator there's nothing to modify.
5. It applies only to the names declared by the declarators, not to names declared incidentally by other specifiers. So the `static` in the example above doesn't give the class `Point` internal linkage; the linkage of a class name is determined by [[basic.link#4]].

```cpp error
thread_local int x;
extern int x;                  // error: every declaration of x must have thread_local
typedef static int SI;         // error: typedef can't combine with a storage class specifier
static struct T { };           // error: no declarator
```

Clang 23 gives only a warning for the last line; a warning also meets the diagnostic requirement. Note 1 points out that explicit specializations ([[temp.expl.spec]]) and explicit instantiations ([[temp.explicit]]) have additional restrictions on storage class specifiers.

¶2 (note) Variables declared in a block and function parameters have automatic storage duration by default if they have no storage class specifier.

## static (¶4)

¶4 `static` can only be used in declarations of variables and functions, structured binding declarations and declarations of anonymous unions. There can be no `static` function declarations in a block, and function parameters can't be `static`. On a variable, it gives the variable static storage duration ([[basic.stc.static]]); together with `thread_local`, thread storage duration.

The effect of `static` in each position is some combination of two things, giving static storage duration and determining linkage:

| Position | Effect of `static` | Basis |
|---|---|---|
| Variables and functions at namespace scope | Internal linkage (variables already have static storage duration) | [[basic.link#3]] |
| Variables in a block | Static storage duration, initialized the first time control passes through the declaration | [[basic.stc.static]], [[stmt.dcl]] |
| Data members of a class | Static data member, not part of any object | [[class.static.data]] |
| Member functions of a class | Static member function, no `this` | [[class.static.mfct]] |
| Anonymous unions at namespace scope | Required when the enclosing namespace has external linkage | [[class.union.anon#2]] |
| Function declarations in a block, function parameters | Ill-formed | ¶4 |

```cpp error
void f() {
    static void g();         // error: can't declare a static function in a block
}
void h(static int x);        // error: a parameter can't be static
union { int a; float b; };   // error: an anonymous union in the global namespace must be static
```

A function declaration in a block always refers to some function at namespace scope and inherits its linkage from earlier declarations. Writing `static` in a block to express internal linkage would be useless when the function can't be defined in the block anyway (a function definition is not a block declaration, [[dcl.pre#1]]), and both C and C++ forbid it.

## thread_local (¶3)

¶3 `thread_local` indicates that the entity has **thread storage duration** ([[g:thread-storage-duration|thread storage duration]], [[basic.stc.thread]]): each thread has its own copy of the object, destroyed when the thread ends. It can only be used on variables at namespace or block scope, structured binding declarations and static data members, not on non-static data members or functions.

In a block, `thread_local` **implies `static`** when no other storage class specifier accompanies it. So a block-scope `thread_local` variable isn't an automatic variable created anew on each entry to the block; there's one per thread, retained across calls:

```cpp run ok
#include <thread>
#include <cstdio>
struct S { static thread_local int per_thread; };
thread_local int S::per_thread = 0;          // the definition of the static data member also needs thread_local

int next_id() {
    thread_local int id = 0;                 // implies static
    return ++id;
}

int main() {
    next_id(); next_id();
    std::thread t([] { std::printf("worker: %d\n", next_id()); });   // the new thread starts at 1
    t.join();
    std::printf("main: %d\n", next_id());                             // 3
}
```

```cpp error
struct S { thread_local int m; };     // error: a non-static data member can't be thread_local
thread_local void f();                // error: a function can't be thread_local
```

!!! impl "TLS and wrapper functions"
    Mainstream platforms implement `thread_local` with the TLS mechanism provided by the operating system and the dynamic linker (the ELF `.tbss` and `.tdata` sections; access may go through `__tls_get_addr`). When a variable needs dynamic initialization or has a non-trivial destructor, the Itanium C++ ABI generates a wrapper function (symbol name starting with `_ZTW`) and an initialization function (`_ZTH`) for it. Other translation units first call the wrapper when accessing the variable, to make sure this thread's initialization has completed, so accessing an external `thread_local` variable can be much more expensive than accessing an ordinary global. When constant initialization is guaranteed, writing `constinit thread_local` ([[dcl.constinit]]) removes this layer of wrapping.

## extern (¶5, ¶7)

¶5 `extern` can only be used in declarations of variables and functions, not on class members or function parameters. The `extern` in `extern template` (an explicit instantiation declaration) and in `extern "C"` (a linkage specification) is not a storage class specifier (note 3).

```cpp run ok
extern const int limit = 100;   // definition: it has an initializer; extern gives the const variable external linkage
extern int later;               // a declaration, not a definition
int later = 5;                  // definition
int use() {
    extern int later;           // extern in a block: refers to the global later
    return later + limit;
}
int main() { return use() - 105; }
```

The effects of `extern` are spread over several subclauses:

1. Without an initializer, it makes the declaration not a definition ([[basic.def#2]]). `extern int x = 1;` is a definition.
2. It affects linkage. A const variable at namespace scope has internal linkage by default, and external linkage with `extern` ([[basic.link#3]]); when an earlier declaration has internal linkage, an `extern` declaration inherits it (see ¶6).
3. `extern int n;` in a block declares a member of the enclosing namespace, while the name is bound only in the block ([[dcl.meaning.general#3.5]]). It can't have an initializer, because an initializer may only appear on a variable declaration whose target scope is the scope in which it appears ([[dcl.decl.general#4]]).

```cpp error
struct X { extern int a; };     // error: can't be used on a class member
void f() { extern int y = 1; }  // error: an extern declaration in a block can't have an initializer
```

¶7 A class that has been declared but not yet defined can appear in `extern` declarations, but only in ways that don't need a complete type:

```cpp error
struct S;
extern S a;           // OK: not a definition, S needn't be complete
extern S f();         // OK
extern void g(S);     // OK
void h() {
    g(a);             // error: passing by value needs S complete
    f();              // error: calls a function returning an incomplete type
}
```

Only definitions require a complete object type ([[basic.def#5]]), so `extern S a;` is valid, and so is `&a`: taking an address doesn't need a complete type.

## All declarations must have the same linkage (¶6)

¶6 All declarations of an entity must give it the same linkage. Note 4 adds: the linkage given by some declarations is affected by earlier declarations; overloaded functions are distinct entities and don't affect each other.

The gist of Example 1 in the standard:

| First | Then | Result |
|---|---|---|
| `static char* f();` | `char* f() {…}` | OK, still internal linkage |
| `char* g();` | `static char* g() {…}` | error: inconsistent linkage |
| `void h();` | `inline void h();` | OK, external linkage; `inline` doesn't affect linkage |
| `static void n();` | `inline void n();` | OK, internal linkage |
| `static int b;` | `extern int b;` | OK, `b` still has internal linkage |
| `int c;` | `static int c;` | error: inconsistent linkage |
| `extern int d;` | `static int d;` | error: inconsistent linkage |
| `static int a;` | `int a;` | error: two definitions |

Internal followed by `extern` works, but not the other way round. `extern` means "refer to an existing entity", so if an earlier declaration is visible, its linkage is kept; `static` actively declares internal linkage. If the latter were allowed to override the former, the same name would refer to different entities in the earlier and later parts of a translation unit.

```cpp run ok
static int counter;          // internal linkage
extern int counter;          // still internal linkage
static void helper();
void helper() { }            // still internal linkage
void f(int);                 // external linkage
static void f(char);         // OK: overloads are distinct entities
static void f(char) { }
int main() { helper(); f('x'); return counter; }
```

The error in the last row of the table is not about linkage: `int a;` inherits internal linkage, but it is also a definition itself, so `a` has two definitions ([[basic.def.odr]]). Clang 23's error says that a non-static declaration follows a static declaration; the reason given by the standard's example is the two definitions.

## mutable (¶8–9)

¶8 `mutable` can only be used on **non-static data members**, and the member's type must be neither const-qualified nor a reference type.

```cpp run ok
#include <mutex>
class Cache {
    mutable std::mutex m;          // can be locked even in const member functions
    mutable int hits = 0;          // statistics
    int value = 42;
public:
    int get() const {
        std::lock_guard lk(m);     // m isn't const, so lock() is allowed
        ++hits;                    // OK
        return value;
    }
};
int main() { const Cache c; return c.get() - 42; }
```

```cpp error
class X {
    mutable const int* p;     // OK: p itself isn't const; it points to const int
    mutable int* const q;     // error: q itself is const
    mutable int& r;           // error: reference type
    mutable static int s;     // error: at most one storage class specifier
};
```

¶9 (note) `mutable` cancels the const of the enclosing object: the member can be modified even if the object is const ([[basic.type.qualifier]]). Accessing a mutable member through a const object yields a non-const lvalue ([[expr.ref]]). A mutable member is not a const object, so modifying it is not the UB of modifying a const object described in [[dcl.type.cv#4]].

`mutable const int` contradicts itself; a reference can't be rebound, so `mutable` means nothing for it either; hence both are forbidden.

The `mutable` in a lambda's `[x]() mutable { ++x; }` is a lambda specifier ([[expr.prim.lambda.general]]); it makes the closure's function call operator not a const member function and has nothing to do with this subclause.

## The retirement of auto and register

!!! history
    - The storage class specifiers in C++98/03 were `auto`, `register`, `static`, `extern` and `mutable`. `auto` explicitly meant automatic storage duration, the same as the default, and was almost never used; `register` was a hint for register allocation.
    - C++11 turned `auto` into a placeholder type specifier ([[dcl.spec.auto]]), on the grounds that the old usage barely existed; it also added `thread_local` and deprecated `register`.
    - C++17 removed `register` as a storage class specifier ([[P0001R1]]); the keyword is reserved for future use. In C, `register` is still valid.

```cpp error
void f() {
    register int x = 0;    // error: register is not a storage class specifier since C++17
    auto int y = 0;        // error: auto is not a storage class specifier since C++11
}
```

Clang 23 reports an error for `register`; the diagnostic belongs to `-Wregister` and can be turned off for compatibility with C headers. For `auto int` it gives only a `-Wauto-storage-class` warning. By the standard both are ill-formed.

## Common misconceptions

!!! pitfall "A static global variable has a different storage duration from an ordinary global"
    Variables at namespace scope already have static storage duration; `static` only changes the linkage.

!!! pitfall "An extern declaration can't have an initializer"
    An `extern` declaration at namespace scope can have an initializer, and such a declaration is a definition. Only `extern` declarations in a block can't.

!!! pitfall "A const global variable has external linkage"
    That's true in C. In C++, a non-volatile const variable at namespace scope has internal linkage by default ([[basic.link#3]]). There are four exceptions: `extern` is written explicitly; it is an `inline` variable; an earlier declaration without internal linkage exists; or it is declared in a module interface unit or module partition. In the last case the general rules give it external or module linkage ([[basic.link#4]]), so `const int N = 10;` from a header changes meaning when moved into a module interface.

## Questions

!!! question "Question 1"
    Is the following program well-formed? Are the two `x`s the same entity?
    ```cpp
    namespace {
        int x;
    }
    extern int x;
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed, and they are two entities. `extern int x;` is in the global namespace, declares `::x`, and has external linkage; the `x` in the unnamed namespace has internal linkage. Their target scopes differ, so they don't conflict.

But writing `x` at global scope afterwards is ambiguous: the unnamed namespace comes with an implicit using-directive, so unqualified lookup finds both `x`s ([[basic.lookup.unqual]], [[namespace.unnamed]]). Clang 23 reports at `int y = x;` that the reference to `x` is ambiguous.
</details>

!!! question "Question 2"
    After `struct A { mutable int n; }; const A a{1};`, what is the behavior of `const_cast<A&>(a).n = 2;` and of `a.n = 2;`? And without `mutable`?

<details markdown="1">
<summary>Answer</summary>

With `mutable`, both are well-formed with defined behavior: `a.n` is itself a non-const lvalue ([[expr.ref]]), and `n` is not a const object. Without `mutable`, `a.n = 2;` is ill-formed because it assigns to a const lvalue; `const_cast<A&>(a).n = 2;` compiles, but `a.n` is a subobject of a const object, and modifying it is UB ([[dcl.type.cv#4]]).
</details>
