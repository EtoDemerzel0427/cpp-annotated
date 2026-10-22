---
title: Grammar summary
summary: "Annex A collects the grammar productions of every chapter in one place, for reference only: it accepts a superset of valid C++ and is ambiguous, and how a piece of code parses often has to be settled by name lookup and disambiguation rules."
updated: 2026-10-19
---

!!! tldr
    - Annex A is an informative summary of the grammar; the normative versions are the same productions in the subclauses of the main text. When citing grammar, cite the main-text subclause.
    - This grammar accepts a superset of valid C++; many restrictions are written in the prose rules of the main text. It is also ambiguous: the same token sequence can have several derivations.
    - Whether an identifier is a type name, a template name or an ordinary variable changes how a whole statement parses, so C++'s grammar is not context-free.
    - The hard-to-parse places are decided by rules outside the grammar: if it can be a declaration, it is one; when `<` starts a template argument list; when `>>` splits into two `>`; and `[[` can only introduce an attribute.

## Same tokens, different parses

```cpp run ok
struct T { T() {} };
int U(int x) { return x; }
int v = 0;

void f() { T(v); }   // declaration: equivalent to T v;, hiding the global v
void g() { U(v); }   // expression: calls U with ::v as the argument
```

`T(v);` and `U(v);` have exactly the same arrangement of tokens; the only difference is the result of name lookup: `T` is a class, `U` is a function. Only after lookup finds that `T` is a class does `T(v);` gain a second reading, namely declaring a variable named `v` of type `T`, with a redundant pair of parentheses around the declarator. Per [[stmt.ambig#1]], if it can be a declaration, it is one. Clang 23 gives a `-Wvexing-parse` warning for `f`, pointing out that the parentheses were taken as part of the declarator.

So the grammar productions alone aren't enough to determine what a piece of C++ code means. Annex A says so itself.

## What Annex A is

Annex A [gram] gathers the grammar productions from the start of each subclause of the main text into one place, in chapter order, adding no new rules. The notation of the productions (italic nonterminals, the subscript opt, *X-seq*, *X-list* and so on) is explained in [[syntax]].

!!! std
    This summary of C++ grammar is intended to be an aid to comprehension. It is not an exact statement of the language.

[gram.general] ¶1 says this summary is only an aid to comprehension, not an exact statement of the language, and names two ways in which it is inexact.

### It accepts a superset of valid C++

```cpp error
int;                           // matches the grammar of simple-declaration
struct A { virtual int x; };   // matches the grammar of member-declaration
```

Both lines can be derived from the grammar, yet both are ill-formed. The first violates [[dcl.pre#6]]: omitting the declarator is allowed only when declaring a class or enumeration. The second violates [[dcl.fct.spec]]: `virtual` can only be used on non-static member functions. Clang 23 gives an error for the second line and only a `-Wmissing-declarations` warning for `int;`; a warning counts as a diagnostic, so that conforms too.

These constraints aren't written into the grammar because the productions would balloon if they were. The first alternative of *member-declaration* consists of attributes, a specifier sequence and a declarator list, all three optional; expressing in productions which specifiers can combine with which declarators would mean splitting every combination into a separate nonterminal. The standard's approach is to describe the shape loosely in the grammar and restrict it with "shall" rules.

### It is ambiguous

The same token sequence can have more than one parse tree; the `T(v);` at the start is an example. ¶1 names three disambiguation rules, [[stmt.ambig]], [[dcl.spec]] and [[class.member.lookup]], for distinguishing expressions from declarations. Beyond that, access control, ambiguity checks and type rules rule out constructs that are grammatically valid but meaningless.

Real compilers therefore need two things outside the grammar: the results of name lookup, and rules for choosing when both derivations work. GCC, Clang and MSVC all use hand-written recursive descent parsers that do name lookup while parsing, and when necessary first parse tentatively as a declaration, backtracking to parse as an expression if that fails.

## Names introduced by declarations

[gram.key] ¶1 says that typedef, namespace, class, enumeration and template declarations introduce new **context-dependent keywords** into the program, and then lists these nonterminals:

| Nonterminal | Forms | Introduced by | Details |
|---|---|---|---|
| *typedef-name* | *identifier*, *simple-template-id* | typedef, alias declarations, alias templates | [[dcl.typedef]] |
| *namespace-name* | *identifier*, *namespace-alias* | Namespace definitions | [[namespace.def]] |
| *namespace-alias* | *identifier* | Namespace alias definitions | [[namespace.alias]] |
| *class-name* | *identifier*, *simple-template-id* | Class declarations, class templates | [[class.name]] |
| *enum-name* | *identifier* | Enumeration declarations | [[dcl.enum]] |
| *simple-template-name* | *identifier* | Template declarations | [[temp.names]] |

"Keyword" here doesn't mean a reserved spelling in the sense of [[lex.key]]; `int` is `int` everywhere. It means that an ordinary identifier, once introduced by some declaration as a type name or template name, changes how subsequent tokens are parsed, just as a keyword would. The `T` at the start is like this.

This dependence comes from C. A C typedef name also changes parsing: `a * b;` is a declaration when `a` is a typedef name, and a multiplication otherwise. The traditional C compiler approach is to have the lexer consult the symbol table and hand typedef names to the parser as a separate kind of token. C++ extends this dependence to class names, template names and namespace names, and so in templates there are situations that even consulting the symbol table can't resolve: a dependent name can't be looked up at the template definition, so only the programmer can tell the parser, with `typename` and `template` ([[temp.res]], [[temp.names#7]]).

The table isn't complete. *concept-name* ([[temp.concept]]) is also an identifier introduced by a template declaration, but it isn't in the list in [gram.key].

## Hard-to-parse code

In each of the following examples, the grammar allows more than one reading, or the reading it gives differs from intuition. What decides in the end is rules outside the grammar.

### `T(x);`: if it can be a declaration, it is one

```cpp run error
struct T { T(int) {} T() {} };
void f() {
  int x = 1;
  T(x);        // declares T x;, rather than constructing a temporary from x
               // error: redefinition of x
}
```

If `T` is a type name, `T(x);` can be either an expression statement starting with a function-style cast or a declaration with a parenthesized declarator. [[stmt.ambig#1]] chooses the declaration. Clang 23 first gives a `-Wvexing-parse` warning and then reports the redefinition of `x`.

This rule has a few details:

- Disambiguation is purely syntactic ([[stmt.ambig#3]]). Apart from whether a name is a type name, the other meanings of names play no part. Disambiguation comes first, so a statement judged to be a declaration may be an ill-formed declaration, and the compiler won't go back and reparse it as an expression.
- Sometimes the whole statement has to be examined to decide. `T(a)->m = 7;` can't be a declaration, so it's an expression; `T(*d)(int);` can be a declaration, so it is one. See the examples in [[stmt.ambig#2]].
- The same rule applies inside declarations too; this is the so-called most vexing parse: `S w(int());` declares a function, not an object ([[dcl.ambig.res#1]]).
- Ambiguities between a type and an expression are resolved as "if it can be a *type-id*, it is one" ([[dcl.ambig.res#2]]), so the `int()` in `X<int()>` is a function type, not a value-initialization expression.

!!! lawyer "`sizeof(int())` is now an expression"
    `sizeof(int())` used to have two derivations: `sizeof ( type-id )` where the *type-id* is the function type `int()`, or `sizeof unary-expression` whose operand is the parenthesized value-initialization `(int())`. By "if it can be a *type-id*, it is one", the former used to be chosen, and it was then ill-formed for applying `sizeof` to a function type.

    The current draft changes the *type-id* in `sizeof`, `alignof`, C-style casts, the parenthesized form of `new` and trailing return types to *nofun-type-id* ([[dcl.name]]), which can't denote a function type. The former derivation no longer works, the ambiguity disappears, and `sizeof(int())` is simply `sizeof(int)`. Note 2 of [[dcl.ambig.res#2]] says exactly this. Here the ambiguity was removed by changing the grammar itself. At the time of writing, Clang 23 still follows the old rule and reports `invalid application of 'sizeof' to a function type`.

### `a < b > (c)`: comparison or template arguments?

```cpp run ok
template<int N> int a(int x) { return N + x; }
constexpr int b = 2;
int r1 = a < b > (3);            // a is a template: a<b>(3), r1 == 5

namespace n {
  int a = 1, b = 2, c = 3;
  bool r2 = (a < b) > (c);       // here a is an int: two comparisons
}
```

`a < b > (c)` can be either two comparisons, `(a < b) > (c)`, or a call to the specialization `a<b>(c)` of template `a`. The deciding factor is [[temp.names#7]]: `<` is taken as the start of a template argument list only in certain cases, chiefly when the name before it is found by lookup to be a template (¶7.3.2), or when it is an unqualified name for which lookup finds one or more functions or finds nothing (¶7.3.3).

In `namespace n`, writing `a < b > (c)` without the parentheses is well-formed according to the standard, and the result is `false`. But by default Clang 23 reports the error `chained comparison 'X < Y > Z' does not behave the same as a mathematical expression`, a `-Wparentheses` diagnostic that is an error by default and can be turned off. That's why the example adds the parentheses.

Taking `<` as the start of a template argument list when lookup finds nothing is a C++20 change ([[P0846R0]]), made so that ADL can find function templates:

```cpp run ok
namespace N {
  struct S {};
  template<int> void h(S) {}
}
void t() {
  N::S s;
  h<0>(s);   // OK since C++20: lookup of h finds nothing, so < starts a template argument list,
             // and then ADL finds N::h in N
}
```

Under C++17 rules `h` is undeclared, and this line is ill-formed. Clang 23 accepts it as an extension with `-std=c++17`, giving a `-Wc++20-extensions` warning.

In templates, a dependent qualified name finds nothing at the point of definition, so the parser has no way to decide and `template` has to be written, as in `p->template alloc<200>()` in Example 1 of [[temp.names#7]].

### `>>` ends two levels of template argument lists

```cpp
template<int> struct X {};
template<class> struct Y {};
Y<X<1>> x3;          // OK: >> treated as two >
Y<X<(6>>1)>> x5;     // OK: >> inside parentheses is still a right shift
Y<X<6>>1>> x4;       // error: the first >> ends X<6> and Y<...>, and the rest can't be parsed
```

Lexing by longest match ([[g:maximal-munch]]) always cuts `>>` into a single token ([[lex.pptoken#5]]). [[temp.names#8]] adds a rule at the parsing stage: within a template argument list, the first non-nested `>` is the terminator, and the first non-nested `>>` is treated as two consecutive `>`, the first of which ends the current list. Non-nested means not inside parentheses, so the way `x5` is written keeps the right shift inside the template argument. Before C++11 there was no such rule, and `Y<X<1>>` had to be written `Y<X<1> >`.

### `<::` and `[::`: exceptions to longest match

```cpp run ok
#include <vector>
struct S {};
std::vector<::S> v;   // < is a token on its own; ::S is a globally qualified name
int i = 1;
int arr[3];
int j = arr[::i];     // [ is a token on its own; ::i is the subscript
```

`<:` is the digraph for `[` ([[lex.digraph]]), and `[:` is the splice delimiter of static reflection. By longest match, `vector<::S>` would be cut into `vector <: :S>`, that is, `vector[:S>`. [[lex.pptoken#5]] specifies exceptions for this:

- ¶5.2: when the character after `<::` is neither `:` nor `>`, `<` becomes a token on its own;
- ¶5.3: when the character after `[::` isn't `:`, or when `[:>` is encountered, `[` becomes a token on its own.

Here the grammar itself isn't the problem; the problem is how tokens are split. The lexical grammar only says what a token can look like; how the input is actually split is decided by [[lex.pptoken#5]]. The most common consequence is that `x+++++y` is split into `x ++ ++ + y` and is ill-formed, even though `x ++ + ++ y` would form a valid expression.

### `[[` can only introduce an attribute

```cpp run error
int y[5];
void f() {
  y[[] { return 2; }()] = 2;     // error: [[ can only introduce an attribute
  y[([] { return 2; }())] = 2;   // OK: with parentheses the two [ are no longer adjacent
}
```

The grammar of an attribute specifier is `[ [ attribute-list ] ]`, with the two `[` being separate tokens. So `[[` could also be the `[` of a subscript operator followed by the `[` of a lambda introducer. [[dcl.attr.grammar#9]] simply rules that two consecutive left square brackets can only introduce an attribute specifier or appear within an attribute argument. Where an attribute isn't allowed, `[[` makes the program ill-formed even if it could match some other production.

Attributes can appear in many places; having the parser try things out would be expensive, and hard for people reading the code to follow. One simple blanket rule costs only the occasional extra pair of parentheses.

### `(a)-b`: cast or subtraction?

`(a)-b` can be a C-style cast (converting `-b` to type `a`) or `a` in parentheses minus `b`. There's no dedicated disambiguation clause here: when `a` is a type name only the former derivation works, otherwise only the latter. In templates, a dependent name `T::x` isn't a type by default, so you have to write `(typename T::x)-b` to get a cast ([[temp.res]]).

## A chapter-by-chapter guide

The table below gives, for each subclause of Annex A, which production to start reading from, together with the corresponding main text and this site's guide page.

| Annex subclause | Starting point and key structures | Main text |
|---|---|---|
| A.3 [gram.lex] | *preprocessing-token* and *token*; the literals, *identifier* | [[lex]] |
| A.4 [gram.basic] | The start symbol *translation-unit*; *splice-specifier* | [[basic]] |
| A.5 [gram.expr] | From *primary-expression* all the way to *expression* | [[expr]] |
| A.6 [gram.stmt] | *statement* | [[stmt]] |
| A.7 [gram.dcl] | *declaration*, *simple-declaration*, *declarator* | [[dcl]] |
| A.8 [gram.module] | *module-declaration*, *module-import-declaration* | [[module]] |
| A.9 [gram.class] | *class-specifier*, *member-declaration* | [[class]] |
| A.10 [gram.over] | *operator-function-id*, *literal-operator-id* | [[over]] |
| A.11 [gram.temp] | *template-declaration*, *template-parameter*, *template-id* | [[temp]] |
| A.12 [gram.except] | *try-block*, *handler*, *noexcept-specifier* | [[except]] |
| A.13 [gram.cpp] | *preprocessing-file*, *group-part* | [[cpp]] |

What follows notes only the places in each chapter's grammar that are easy to misread or worth attention.

### Lexing and translation units

- The lexical grammar works in characters and produces preprocessing tokens; phase 7 then converts preprocessing tokens into tokens ([[lex.pptoken]], [[lex.token]]).
- *pp-number* is deliberately looser than numeric literals: `1.2.3` and `0xe+foo` are each a single *pp-number* ([[lex.ppnumber]]).
- *translation-unit* is the start symbol of the whole grammar; its two alternatives are an ordinary translation unit and a module unit ([[module.unit]]). Syntactically a translation unit is just a sequence of declarations; C++ has no top-level statements.

### Expressions: precedence by nesting

There is no operator precedence table in the standard; precedence and associativity are expressed by the nesting of productions. From tightest to loosest:

| Level | Nonterminal | Operators | Details |
|---|---|---|---|
| Primary | *primary-expression* | Literals, `this`, `( )`, names, lambdas, folds, requires, splices | [[expr.prim]] |
| Postfix | *postfix-expression* | `[]` `()` `.` `->` postfix `++ --`, named casts, `typeid`, function-style casts | [[expr.post]] |
| Unary | *unary-expression* | Prefix `++ --`, `* & + - ! ~`, `sizeof`, `alignof`, `co_await`, `noexcept`, `new`, `delete`, `^^` | [[expr.unary]] |
| Cast | *cast-expression* | `( nofun-type-id ) cast-expression` | [[expr.cast]] |
| Pointer-to-member | *pm-expression* | `.*` `->*` | [[expr.mptr.oper]] |
| Multiplicative, additive, shift | *multiplicative-*, *additive-*, *shift-expression* | `* / %`, `+ -`, `<< >>` | [[expr.mul]], [[expr.add]], [[expr.shift]] |
| Three-way comparison | *compare-expression* | `<=>` | [[expr.spaceship]] |
| Relational, equality | *relational-*, *equality-expression* | `< > <= >=`, `== !=` | [[expr.rel]], [[expr.eq]] |
| Bitwise, logical | *and-* through *logical-or-expression* | `& ^ \| && \|\|` | [[expr.bit.and]] etc. |
| Conditional | *conditional-expression* | `?:` | [[expr.cond]] |
| Assignment | *assignment-expression* | `=` etc., `throw`, `co_yield` | [[expr.assign]] |
| Comma | *expression* | `,` | [[expr.comma]] |

- *compare-expression* sits between shift and relational, so `a <=> b < 0` parses as `(a <=> b) < 0`.
- Function-style casts `T(x)` and `T{x}` are in postfix expressions, while the C-style cast `(T)x` is in *cast-expression*; the two have different precedence ([[expr.type.conv]]).
- The right-hand side of an assignment is an *initializer-clause*, so `x = {1, 2}` is grammatically valid.
- *constant-expression* is grammatically just a *conditional-expression*, so a top-level assignment or comma can't be written directly where a constant expression is expected; it needs parentheses.

### Statements and declarations

- *declaration-statement* is just *block-declaration*, so a function can't be defined, nor a template declared, inside a block.
- Most alternatives of *statement* begin with optional attributes, but *declaration-statement* and *labeled-statement* don't; their attributes belong to the grammar of the declaration and the label themselves. C++26 adds *expansion-statement* (`template for`, [[stmt.expand]]) and *assertion-statement* (`contract_assert`, [[stmt.contract.assert]]).
- A *simple-declaration* consists of a specifier sequence on the left and a declarator list on the right, each declarator with its own initializer ([[dcl.spec]], [[dcl.decl]]).
- Declarators have two layers: the prefix `*`, `&`, `&&`, `C::*` are in *ptr-declarator*, and the postfix `()`, `[]` are in *noptr-declarator*, with the postfix ones binding tighter. So `int *a[3]` is an array of pointers, and `int (*a)[3]` is a pointer to an array ([[dcl.meaning]]).
- A *type-id* is a declaration with the name removed, using an *abstract-declarator*; the *nofun-type-id* used in cast expressions can't denote a function type ([[dcl.name]]).
- The content of an attribute argument is a *balanced-token-seq*: any tokens, with only `()`, `[]` and `{}` required to balance. So compilers' vendor attributes can have argument syntax of their own.

### Modules, classes, overloading, templates, exceptions

- The module productions use *module-keyword*, *import-keyword* and *export-keyword* rather than literal `module` and `import`. These three tokens are produced by the preprocessor when it processes module directives and have no visible spelling ([[lex.pptoken#4]]), so in ordinary code `import` and `module` can still be used as identifiers ([[lex.name]]).
- *member-declarator* has more than declarators at namespace scope: `override`, `final`, `= 0`, bit-field widths and default member initializers ([[class.mem]]).
- *operator* lists all the overloadable operators, including `co_await`, `()`, `[]`, `<=>` and `new[]` ([[over.oper]]).
- Template template parameters are subdivided into *type-tt-parameter*, *variable-tt-parameter* and *concept-tt-parameter*, accepting class or alias templates, variable templates and concepts respectively ([[temp.param]]).
- A *requires-clause* only allows primary expressions joined by `&&` and `||`, so `requires sizeof(T) > 4` must be written `requires (sizeof(T) > 4)` ([[temp.pre]]).
- Among the alternatives of *template-argument*, *constant-expression* comes before *type-id*, but when both match, *type-id* is chosen per [[dcl.ambig.res#2]].
- *throw-expression* isn't in the grammar of the exceptions chapter but in the expression grammar ([[expr.throw]]).

### Preprocessing directives

Preprocessing directives have a separate grammar: the input is preprocessing tokens, newlines are meaningful tokens here, and directives are line-based. The start symbol *preprocessing-file* has two alternatives: a sequence of *group*s (an ordinary file), or a *module-file* (a module unit file beginning with a global module fragment or a `module` directive). A *group-part* is a control line (`#include`, `#embed`, `#define` and so on), a conditional inclusion, an ordinary text line, or a conditionally-supported directive. Module and import directives have no `#` ([[cpp.module]], [[cpp.import]]). The overview is in [[cpp.pre]].

## Questions

!!! question "1. Is the `<` in `x = y < z > w;` necessarily a less-than sign?"

<details markdown="1">
<summary>Answer</summary>

Not necessarily. If `y` is an unqualified name for which lookup finds a template, or one or more functions, or nothing at all, then per ¶7.3 of [[temp.names#7]] the `<` starts a template argument list, `y<z>` is a *template-id*, and the following `w` makes the expression unparsable, giving an error. Only when lookup finds a non-function entity such as a variable is it two comparisons.
</details>

!!! question "2. When a production in Annex A disagrees with the production of the same name in the main text, which one wins?"

<details markdown="1">
<summary>Answer</summary>

The main text. Annex A is informative; [gram.general] ¶1 says outright that it is not an exact statement of the language, and the normative grammar is in the subclauses of the main text. In the standard's source files Annex A is generated automatically from the grammar blocks of the main text, so the two ought to agree; if they don't, it's an editorial error.
</details>

!!! question "3. Is `T(a)[5];` a declaration or an expression? `T` is a class type."

<details markdown="1">
<summary>Answer</summary>

A declaration: it declares a variable named `a` of type array of 5 `T`. It can syntactically be a declaration (with declarator `(a)[5]`), so per [[stmt.ambig#1]] it is one. Example 1 of [[stmt.ambig#2]] has the same example, `T(e)[5];`.
</details>
