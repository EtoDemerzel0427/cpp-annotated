---
title: Syntax notation
summary: "How to read the grammar productions in the standard: nonterminals and terminals, one alternative per line, one of, the subscript opt, and the suffixes -name, -id, -seq and -list; then a few real productions used to answer practical questions about precedence and how to read declarations."
updated: 2026-10-18
---

!!! tldr
    - Before the colon of a production is the syntactic category being defined; each line below is one alternative. Italic words are other syntactic categories, monospaced words and symbols must be written as is, and the subscript opt marks something optional.
    - Name suffixes have fixed meanings: -seq is several written one after another, -list is several separated by commas, -name needs name lookup to be determined, and -id does not depend on context.
    - The standard has no operator precedence table; precedence and associativity follow from how the expression productions nest.
    - The declarator productions explain why declarations are read starting from the name, from the inside out.
    - Matching the grammar does not make code valid. Disambiguation, name lookup and type rules rule out a great deal of grammatical code.

## Reading a production (¶1)

The grammar of the `if` statement is in [[stmt.select.general]]:

```text
selection-statement:
    if constexpr_opt ( init-statement_opt condition ) statement
    if constexpr_opt ( init-statement_opt condition ) statement else statement
    if !_opt consteval compound-statement
    if !_opt consteval compound-statement else statement
    switch ( init-statement_opt condition ) statement
```

*selection-statement*, before the colon on the first line, is the syntactic category this production defines. Each indented line below is one alternative; code that matches any one of them is a *selection-statement*.

The words in a line come in two kinds. Hyphenated lowercase words like *init-statement*, *condition* and *statement* are other syntactic categories, also called nonterminals, each with its own production. `if`, `constexpr`, `(` and `else` are terminals and must appear literally in the source. Components marked `_opt` may be omitted.

¶1 This is the notation [syntax] specifies. In the standard's text:

- syntactic categories are in italic sans-serif type, such as *expression*; terminals are in constant-width type, such as `if` and `::`;
- alternatives are listed on separate lines; when there are many, "one of" marks several alternatives written on one line;
- when an alternative is too long for one line, the continuation line is indented further than the first;
- an optional component carries the subscript opt; for example { *expression*<sub>opt</sub> } means the braces may contain an expression or not.

!!! tip "How this site writes it"
    On eel.is, opt appears as a subscript. When a production is copied as plain text, the subscript runs into the preceding word, giving `expressionopt` and `constexpropt`. In code blocks this site writes `expression_opt` and drops the italics.

An example of "one of" is the assignment operators in [[expr.assign]]; each token on the line is a separate alternative:

```text
assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

An example of a continuation line is *parameters-and-qualifiers* in [[dcl.decl.general]]; the second line is indented one more level, and together with the first line it forms a single alternative:

```text
parameters-and-qualifiers:
    ( parameter-declaration-clause ) cv-qualifier-seq_opt
        ref-qualifier_opt noexcept-specifier_opt attribute-specifier-seq_opt
```

### What selection-statement tells you

Back to the production for `if`, item by item:

- `constexpr` may be omitted, so `if` and `if constexpr` share one production ([[stmt.if]]).
- *init-statement* may be omitted; this is C++17's `if` with an initializer. Note 1 explains that an *init-statement* ends with a semicolon, so the semicolon in `if (auto n = v.size(); n > 2)` belongs to the *init-statement*, not to the `if` syntax as a separator.
- `!` may be omitted, giving `if consteval` and `if !consteval`.
- After `consteval`, a *compound-statement* is required, not an arbitrary *statement*, so the braces cannot be omitted.

<div class="compare" markdown="1">

```cpp run error
constexpr int f() {
  if consteval return 1;   // error
  return 0;
}
```

```cpp run ok
constexpr int f() {
  if consteval { return 1; }
  return 0;
}
```

</div>

`if constexpr (B) return 1;` has no such restriction, because the parenthesized condition already separates the condition from the statement. `if consteval` has no parentheses; if any statement were allowed, `if consteval return 1;` would read as if `consteval` modified `return`.

```cpp run ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  if (auto n = v.size(); n > 2) { }       // init-statement and condition
  if constexpr (sizeof(int) == 4) { }     // constexpr_opt
  if !consteval { }                       // !_opt consteval compound-statement
  switch (int k = 2; k) { case 2: break; }
}
```

## Name suffixes (¶2)

¶2 The names of syntactic categories are generally chosen according to the following rules:

| Form | Meaning | Examples |
|---|---|---|
| *X-name* | An identifier whose meaning is determined by its context | *class-name*, *typedef-name*, *template-name* |
| *X-id* | An identifier (or combination of identifiers) whose meaning does not depend on context | *qualified-id*, *unqualified-id*, *type-id* |
| *X-seq* | One or more *X*s with no intervening delimiters | *decl-specifier-seq*, *attribute-specifier-seq*, *statement-seq* |
| *X-list* | One or more *X*s separated by commas | *identifier-list*, *init-declarator-list*, *template-argument-list* |

### -seq and -list: repetition through recursion

Productions have no symbol for repetition; repetition is written as recursion. The declarator list in [[dcl.decl.general]] is defined like this:

```text
init-declarator-list:
    init-declarator
    init-declarator-list , init-declarator
```

A list is either a single element, or a shorter list followed by a comma and an element. Expanded, that gives `a`, `a, b`, `a, b, c`. In `int a = 1, b, c = 3;`, the part `a = 1, b, c = 3` is an *init-declarator-list*.

### -name: the grammar depends on name lookup

A *class-name* is formally just an identifier; it is a *class-name* only if name lookup finds that it actually names a class. So parsing C++ requires knowing what each name is first:

```cpp run ok
struct T {};
void h(int) {}
int a = 1;
int main() {
  T(x);   // T names a type: declares a variable x of type T
  h(a);   // h names a function: calls h with argument a
  (void)x;
}
```

The two lines have exactly the same form; their meaning depends on whether the name before the parenthesis is a type or a function. This is one of the main reasons C++ is hard to parse, and also why templates need `typename`: at the point of the template definition, the compiler doesn't yet know whether `T::x` is a type, so the programmer has to say so with `typename T::x` ([[temp.res]]).

## Answering practical questions with the grammar

### Operator precedence

The C++ standard has no operator precedence table. A footnote in [[expr.pre]] says that precedence is not directly specified but can be derived from the grammar. The production for each level of expression refers to the syntactic category of the next higher level, and this nesting is the precedence.

The production for assignment expressions is in [[expr.assign]]:

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause
```

The last alternative tells you three things:

1. The left operand is a *logical-or-expression*. A conditional expression `c ? a : b` is not a *logical-or-expression*, so `c ? a : b = 42` cannot take `c ? a : b` as the left operand. [[expr.cond]] specifies that the third operand of a conditional expression is an *assignment-expression*, so the whole thing parses as `c ? a : (b = 42)`. C's grammar is different, and in C this is an error.
2. The right operand is an *initializer-clause*, which may be a braced list, so `x = {3}` is valid.
3. An *initializer-clause* can in turn be an *assignment-expression*, so `x = y = z` parses as `x = (y = z)`: assignment associates right to left.

```cpp run ok
int main() {
  bool c = false;
  int a = 1, b = 2;
  c ? a : b = 42;          // c ? a : (b = 42)
  int x, y, z = 3;
  x = y = z;               // x = (y = z)
  x = {3};                 // the right operand may be a braced list
  return (a == 1 && b == 42 && x == 3 && y == 3) ? 0 : 1;
}
```

*throw-expression* is also an alternative of *assignment-expression*, so `throw` has the same low precedence as assignment, and `cond ? x : throw err` is valid.

### Why declarations are read from the inside out

The grammar of declarators in [[dcl.decl.general]] (excerpt):

```text
ptr-declarator:
    noptr-declarator
    ptr-operator ptr-declarator

noptr-declarator:
    declarator-id attribute-specifier-seq_opt
    noptr-declarator parameters-and-qualifiers
    noptr-declarator [ constant-expression_opt ] attribute-specifier-seq_opt
    ( ptr-declarator )

ptr-operator:
    * attribute-specifier-seq_opt cv-qualifier-seq_opt
    & attribute-specifier-seq_opt
    && attribute-specifier-seq_opt
    nested-name-specifier * attribute-specifier-seq_opt cv-qualifier-seq_opt
```

`*` and `&` belong to *ptr-declarator* and are written to the left of the name; an array's `[]` and a function's `()` belong to *noptr-declarator* and are written to the right of the name. A *noptr-declarator* is a component of a *ptr-declarator*, so the `[]` and `()` on the right bind to the name before the `*` on the left. The only way to make `*` bind first is the last alternative, `( ptr-declarator )`, with parentheses.

Parsing two declarations by this rule:

- `int *const p[3]`: the name `p` first combines with `[3]` into a *noptr-declarator*, so p is an array of 3 elements; then with `*const` into a *ptr-declarator*, so the elements are const pointers. So p is an array of 3 const pointers to int.
- `int (*f)(int) noexcept`: `*f` inside the parentheses first forms a *ptr-declarator*, the parentheses make it a *noptr-declarator*, and then `(int) noexcept` is attached. So f is a pointer to a function that takes an int, returns an int, and does not throw.

```cpp run ok
#include <type_traits>
int main() {
  // one init-declarator-list containing two init-declarators
  int *const p[3] = {}, (*f)(int) noexcept = nullptr;
  static_assert(std::is_same_v<decltype(p), int* const[3]>);
  static_assert(std::is_same_v<decltype(f), int(*)(int) noexcept>);
  (void)p; (void)f;
}
```

The `const` and `&&` qualifiers of member functions also enter the function type here: they are the *cv-qualifier-seq* and *ref-qualifier* in *parameters-and-qualifiers* ([[dcl.fct]]).

## The grammar is only the first filter

### Grammatical code can have several readings

Annex A [[gram]] collects all the productions, but [[gram.general]] explains that this grammar accepts a superset of valid C++ constructs. The same code may have several readings; disambiguation rules ([[stmt.ambig]], [[dcl.ambig.res]]) pick one, and then access control and type rules rule out constructs that make no sense.

The best-known disambiguation rule is: when a statement can be read both as a declaration and as an expression, it is treated as a declaration. This is the most vexing parse:

```cpp run error
struct Timer {};
struct TimeKeeper {
  explicit TimeKeeper(Timer) {}
  int get_time() { return 0; }
};
int main() {
  TimeKeeper time_keeper(Timer());   // declares a function, not an object
  return time_keeper.get_time();     // error: time_keeper is a function
}
```

In a parameter position, `Timer()` can be read as the type of a function taking no parameters and returning Timer, which as a parameter type is adjusted to a function pointer. So the whole line declares a function named `time_keeper`. Using braces, `TimeKeeper time_keeper{Timer{}};`, removes the ambiguity. Clang gives a `-Wvexing-parse` warning for this form.

### Lexing comes before parsing

[[lex]] has another set of lexical productions (*identifier*, *pp-number* and so on) that split the source text into tokens in translation phase 3. Each split takes the longest sequence of characters that can form a token; this is called maximal munch ([[lex.pptoken]]).

```cpp run error
int main() {
  int a = 1, b = 2;
  int c = a+++++b;    // error: split as a ++ ++ + b; the result of a++ cannot be incremented again
}
```

`a++ + ++b` would have been a valid reading, but when tokens are split there is no parsing yet; the lexer greedily produces `++`, `++`, `+`. One exception is `>>` in a template argument list: since C++11, the `>>` at the end of `vector<vector<int>>` is treated as two `>` ([[temp.names]]).

!!! note "Cite productions from the main text"
    Annex A is an informative summary and occasionally differs editorially from the main text. When citing a production, cite the subclause that defines it.

## Questions

!!! question "Question"
    By the grammar of *assignment-expression*, how does `a = b ? c : d = e` parse? Is `(a ? b : c) = d` grammatically valid?

<details markdown="1">
<summary>Answer</summary>

In `a = b ? c : d = e`, the left operand `a` is a *logical-or-expression*, and the *initializer-clause* on the right is the *assignment-expression* `b ? c : d = e`. That in turn is a conditional expression whose third operand is the *assignment-expression* `d = e`. So the whole is `a = (b ? c : (d = e))`.

`(a ? b : c) = d` is parenthesized, so the left side is a *primary-expression*, which is also a *logical-or-expression*, so it is grammatically valid. Whether it can be assigned to is decided by the semantics: when `b` and `c` are lvalues of the same type, the result of the conditional expression is an lvalue and can be assigned to ([[expr.cond]]).
</details>
