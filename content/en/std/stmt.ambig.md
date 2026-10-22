---
title: Ambiguity resolution (expression statements versus declarations)
summary: "A statement of the form T(x); can be read both as a function-style type conversion and as a declaration, and the standard says that whatever can be read as a declaration is one; the decision is purely syntactic and sometimes needs the whole statement; C++23's auto(x) brought an extra rule about trailing return types."
updated: 2026-10-19
---

!!! tldr
    - `T(x);` can be an expression statement converting `x` to `T`, or the declaration `T x;`. As long as the whole statement can be read as a declaration, it is a declaration.
    - Deciding whether it can be read as a declaration sometimes requires looking at the whole statement: `T(a)->m = 7;` is an expression, `T(*d)(int);` is a declaration.
    - The decision is based only on syntax and on whether each name is a type name. Once read as a declaration, it does not fall back to an expression even if the declaration itself is erroneous.
    - `std::unique_lock<std::mutex>(m);` declares a lock named `m` and does not lock the global `m`. RAII guard objects need names.
    - When a statement can be read as a declaration with a trailing return type, it counts as a declaration only if it begins with `auto` (an extra rule prompted by C++23's `auto(x)`).

## One line of code, two readings

```cpp
#include <mutex>
std::mutex m;
int counter;
void inc() {
    std::unique_lock<std::mutex>(m);   // declares a local lock named m; the global m is not locked
    ++counter;                         // not locked
}
```

This code compiles, yet locks nothing at all. C's declaration syntax allows parentheses around a declarator, so `int (x);` is the same as `int x;`; and C++ also has the function-style type conversion `T(x)` ([[expr.type.conv]]). So `T(x);` has two readings:

- an expression statement: convert `x` to `T`, then discard the result;
- a declaration: declare a variable of type `T` named `x`, with redundant parentheses.

¶1 The standard specifies that an expression statement with a function-style explicit type conversion as its leftmost subexpression, if it is indistinguishable from a declaration whose first declarator starts with `(`, **is treated as a declaration** (with one exception in ¶4). The line above is therefore `std::unique_lock<std::mutex> m;`: a default-constructed lock that hides the global `m` and is associated with no mutex.

Declaration is chosen partly because `int (x);` has always been a declaration in C, and partly because parenthesized declarators are indispensable anyway, as in the function pointer `T (*p)(int);`. [[dcl.ambig.res]] handles ambiguities inside declarations (function or object), and [[stmt.pre#7]] handles ambiguities in conditions, both in the same direction: whatever can be a declaration is a declaration.

For this line, Clang 23 gives a `-Wvexing-parse` warning saying the parentheses were taken as redundant parentheses around the declaration of the variable `m`. Using `std::lock_guard`, which has no default constructor, would instead fail to compile for lack of a matching constructor, which is actually better.

The correct way is to name the guard:

| Form | Effect |
|---|---|
| `std::unique_lock<std::mutex> lk(m);` | correct |
| `std::unique_lock lk{m};` | correct, with template arguments deduced by CTAD |
| `std::unique_lock<std::mutex>{m};` | an expression statement: the temporary lock is released at the end of the statement |
| `(std::unique_lock<std::mutex>(m));` | same as above |

The last two are no longer declarations, but the temporary is destroyed at the end of the full-expression and the lock released immediately, so they do not work either.

## The whole statement may need to be examined (¶2)

¶2 (Note) If a statement cannot syntactically be a declaration, there is no ambiguity and the rule does not apply. Deciding whether it can be a declaration sometimes requires examining the whole statement, not just its first few tokens. Example 1 in the standard assumes `T` is a simple type specifier:

| Statement | Result | Reason |
|---|---|---|
| `T(a)->m = 7;` | expression | `->m` cannot appear in a declarator |
| `T(a)++;` | expression | a declarator cannot be followed by `++` |
| `T(a,5)<<c;` | expression | `(a,5)` is not a declarator |
| `T(*d)(int);` | declaration | `d` is a pointer to the function `T(int)` |
| `T(e)[5];` | declaration | `e` has type `T[5]` |
| `T(f) = { 1, 2 };` | declaration | `f` with an initializer |
| `T(*g)(double(3));` | declaration | `g` is a `T*`, with the initializer `double(3)` |

As a declaration, the last line is ill-formed: a `double` cannot initialize a `T*`. But parsing ignores semantics; if it can be parsed as a declaration, it is a declaration.

The remaining cases listed in Example 2 of the standard are all declarations too (`T` is a class with the corresponding constructors):

```cpp ok
class T {
public:
    T();
    T(int);
    T(int, int);
};
extern int h;
void f() {
    T(a);             // T a;
    T(*b)();          // b is a pointer to the function T()
    T(c) = 7;         // T c = 7;
    T(d), e, f = 3;   // three variables of type T: d, e, f
    T(g)(h, 2);       // T g(h, 2);
}
```

`T(d), e, f = 3;` read as an expression is a comma expression, but it can also be read as declaring three variables, so it is a declaration.

## Syntax only, no going back (¶3)

¶3 The disambiguation is purely syntactic: apart from whether a name is a *type-name*, the meaning of names neither takes part in the disambiguation nor is changed by it. Class templates are instantiated as necessary to determine whether a qualified name is a type name.

Disambiguation precedes parsing. A statement disambiguated as a declaration may well be an ill-formed declaration, and the compiler does not go back and treat it as an expression because treating it as a declaration produces an error. Example 3 in the standard:

```cpp error
struct T1 {
    T1 operator()(int x) { return T1(x); }
    int operator=(int x) { return x; }
    T1(int) { }
};
struct T2 { T2(int) { } };
int a, (*(*b)(T2))(int), c, d;

void f() {
    T1(a) = 3,
    T2(4),                    // this declares T2 as a variable of type T1
    (*(*b)(T2(c)))(int(d));   // error: T2 is no longer a type name, so this part cannot be parsed
}
```

As an expression, this statement is a comma expression made of assignments and function calls, perfectly valid. But its beginning can also be read as a declaration: `T1(a) = 3` is a declarator with an initializer, and `T2(4)` looks like a declarator named `T2` with the initializer `4`. So disambiguation chooses a declaration. Once `T2` is declared as a variable, the `T2` in the later `T2(c)` is no longer a type name, and the last part fails to parse, by which point there is no going back. The error Clang 23 reports is exactly that `T2` is hidden by a non-type declaration.

The last sentence of ¶3: if, during parsing, lookup finds that a name in a template argument is bound to (part of) the declaration being parsed, the program is ill-formed, no diagnostic required ([[g:ifndr|IFNDR]]): the compiler need not report an error, and the standard places no requirements on such a program.

!!! impl "How compilers implement it"
    Compilers generally use tentative parsing: starting from the beginning of the statement, they try to parse it as a declaration, and decide it is an expression on meeting a token that cannot appear in a declaration (such as `->m` or `++`). The tentative phase does only syntactic checks and type-name lookups, which corresponds exactly to the purely syntactic rule of ¶3. In Example 3, `T2` has not yet been redeclared during the tentative phase, so it is judged a declaration; in the real parse `T2` is already a variable, so parsing fails. In Clang, the corresponding logic is in the `Parser::isCXXDeclarationStatement` family of functions.

## Trailing return types beginning with auto (¶4)

C++23 introduced `auto(x)` and `auto{x}` (decay-copy, [[expr.type.conv]]), so `auto(s)` can also be a function-style type conversion. And `auto f() -> R;` is a function declaration with a trailing return type, which is equally valid with parentheses as `auto(f)() -> R;`. So `auto(s)()->M;` has two readings:

- an expression: copy `s`, call its `operator()`, and access member `M` of the result;
- a declaration: declare a parameterless function `s` with return type `M`.

¶4 An ambiguous statement that can be read as a declaration whose outermost declarator has a trailing return type is treated as a declaration **only if it starts with `auto`**.

The specifier of a function declaration with a trailing return type must be `auto` ([[dcl.fct]]). So such a declaration starting with any other type is necessarily ill-formed, and there is no reason to choose it; and whether it starts with `auto` can be decided from the tokens alone, without violating the purely syntactic requirement of ¶3. Example 4 in the standard:

```cpp ok
struct M;
struct S {
    S* operator()();
    int N;
    int M;
    void mem(S s) {
        auto(s)()->M;      // expression: M here names the member S::M, not a type name
    }
};
void f(S s) {
    {
        auto(s)()->N;      // expression: N is not a type name
        auto(s)()->M;      // declaration: function s with return type ::M
    }
    {
        S(s)()->N;         // expression
        S(s)()->M;         // expression: does not start with auto
    }
}
```

Clang 23 behaves as the standard says: the four expression statements each get an unused-result warning, and only the `auto(s)()->M;` in `f` is treated as a declaration.

## Common misconceptions

!!! pitfall "`T(x);` creates a temporary"
    It declares a variable named `x`. If `x` is already declared in the same scope, this is a redeclaration error; in an inner block, it hides the outer `x`.

!!! pitfall "The compiler picks the more sensible reading by semantics"
    Disambiguation looks only at whether names are type names. Even if treating it as a declaration leads to a semantic error, such as a type with no default constructor, the compiler does not switch to treating it as an expression.

## Questions

!!! question "Question 1"
    `T` is a class type. Is each statement below a declaration or an expression?
    ```cpp
    T(x);           // (a)
    T(x).f();       // (b)
    T(x) + 1;       // (c)
    T(*x);          // (d)
    T(x)(1);        // (e)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) The declaration `T x;`.
- (b) An expression: `.f()` cannot follow a declarator.
- (c) An expression: `+ 1` cannot follow a declarator.
- (d) The declaration `T* x;`.
- (e) The declaration `T x(1);`, directly initializing a `T` named `x` with `1`.
</details>

!!! question "Question 2"
    Why does ¶4 check only whether the statement begins with `auto`, rather than whether the declaration is semantically valid?

<details markdown="1">
<summary>Answer</summary>

Disambiguation must be done at the syntactic level (¶3). Letting semantic checks take part would bring backtracking: first treat it as a declaration, discover a semantic error, then switch to an expression, which is exactly what ¶3 rules out. The specifier of a function declaration with a trailing return type must be `auto` ([[dcl.fct]]), a condition decidable from the tokens alone, which happens to rule out, at the syntactic level, the declarations that would necessarily be ill-formed.
</details>
