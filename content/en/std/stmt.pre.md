---
title: Statements in general, labels, expression and compound statements
summary: "The kinds of statements; substatements and enclosure, which decide where break, case and goto can be written; declarations in conditions and their values, including C++26 structured binding conditions; labels, expression statements and compound statements."
updated: 2026-10-19
---

!!! tldr
    - Where `break`, `case` and `goto` can be written is decided by enclosure. Enclosure is built on substatements, and a lambda body is not a substatement, so none of these statements can cross a lambda.
    - A condition can be an expression or a declaration. The declaration form accepts only `=` or brace initialization, and its specifiers can only be type specifiers and `constexpr`; whatever can be read as a declaration is treated as one.
    - A declaration-form condition tests the result of contextually converting the decision variable to `bool`. A C++26 structured binding condition tests the whole bound object, not any one binding.
    - A label's scope is the whole function. Since C++23 a label can be placed at the end of a block. The branches of `if constexpr` and `if consteval` and the body of an expansion statement are control-flow-limited statements and cannot be jumped into from outside.
    - The expression in an expression statement is a discarded-value expression, and all its side effects are completed before the next statement begins.

## What statements there are (¶1)

¶1 Except as indicated, statements are executed in sequence. The order of evaluations within one statement is determined by the sequenced-before rules of [[intro.execution]]: every full-expression is sequenced before the next full-expression to be evaluated.

| Syntactic category | Example | See |
|---|---|---|
| *labeled-statement* | `L: x = 1;`, `case 3: …` | [[stmt.label]] |
| *expression-statement* | `f(x);`, `;` | [[stmt.expr]] |
| *compound-statement* | `{ … }` | [[stmt.block]] |
| *selection-statement* | `if`, `if constexpr`, `if consteval`, `switch` | [[stmt.select]] |
| *iteration-statement* | `while`, `do`, `for`, range-based `for` | [[stmt.iter]] |
| *expansion-statement* {{c++26}} | `template for (auto x : t) { }` | [[stmt.expand]] |
| *jump-statement* | `break`, `continue`, `return`, `co_return`, `goto` | [[stmt.jump]] |
| *assertion-statement* {{c++26}} | `contract_assert(p);` | [[stmt.contract.assert]] |
| *declaration-statement* | `int x = 0;` | [[stmt.dcl]] |
| *try-block* | `try { } catch (...) { }` | [[except.pre]] |

Except for labeled statements and declaration statements, any statement can be preceded by an attribute sequence, which appertains to that statement. A label's own attributes are written in the label, and the attributes of a declaration statement belong to the declaration itself ([[dcl.pre]]). Common statement attributes are `[[likely]]` and `[[unlikely]]` ([[dcl.attr.likelihood]]), and `[[fallthrough]]` written on a null statement ([[dcl.attr.fallthrough]]).

```cpp run ok
int classify(int n) {
  if (n > 0) [[likely]] {     // the attribute appertains to this compound statement
    return 1;
  }
  switch (n) {
  case 0:
    [[fallthrough]];          // the attribute appertains to a null statement
  case -1:
    return 0;
  default:
    return -1;
  }
}
int main() { return classify(1) == 1 ? 0 : 1; }
```

¶1 also defines a few syntactic pieces reused by several statements:

- *init-statement*: an expression statement, a simple declaration, or, since C++23, an alias declaration ([[P2360R0]]). It is written at the start of `if`, `switch`, `for`, range-based `for` and `template for`, and always ends with a semicolon, which is why `if (auto x = f(); x)` has a semicolon in the middle.
- *condition*: an expression, or a condition declaration. See below.
- *for-range-declaration* and *for-range-initializer*: the declaration to the left of the colon and the initializer to its right in range-based `for` and expansion statements.

## Substatements and enclosure (¶2–¶3)

```cpp run error
void h(int n) {
  for (int i = 0; i < n; ++i) {
    [&] {
      if (i == 3) break;   // error: break is not in a loop
    }();
  }
}
```

The `break` is written inside the braces of the loop, yet it does not count as being in the loop. The reason is that the standard decides what is "inside" by substatements and enclosure, and a lambda body is not a substatement.

### Substatements (¶2)

¶2 The [[g:substatement|substatements]] of a statement are:

| Outer statement | Its substatements |
|---|---|
| labeled statement (¶2.1) | the statement after the label |
| compound statement (¶2.2) | each statement in it |
| selection statement (¶2.3) | each branch, not including the *init-statement* |
| iteration statement (¶2.4) | the loop body, not including the *init-statement* |
| expansion statement (¶2.5) | its compound statement, not including the *init-statement* |

Note 1 points out that the function body of a lambda expression is not a substatement of the statement containing it. A lambda body is the body of another function, and control cannot jump from there into a loop or `switch` of the enclosing function. A condition is not a statement, so naturally it is not a substatement either.

### Enclosure (¶3)

¶3 A statement S1 **encloses** a statement S2 if and only if:

- ¶3.1 S2 is a substatement of S1;
- ¶3.2 S1 is a selection, iteration or expansion statement and S2 is its *init-statement*;
- ¶3.3 S1 is a *try-block* and S2 is its compound statement or the compound statement of one of its handlers;
- ¶3.4 or S1 encloses some S3 that encloses S2.

Conversely, S2 is said to be enclosed by S1. Enclosure can span any number of levels, but not function boundaries. Many rules are phrased in terms of it:

- `break` and `continue` must be enclosed by a loop, a `switch` or an expansion statement ([[stmt.break]], [[stmt.cont]]);
- `case` and `default` labels must be enclosed by a `switch` ([[stmt.label#2]]);
- a coroutine shall not enclose a `return` statement ([[stmt.return.coroutine#1]]);
- a fallthrough statement must appear within an enclosing `switch` ([[dcl.attr.fallthrough#1]]).

Handlers are within the enclosure relation too (¶3.3), so a `break` in a `catch` block can leave an outer loop:

```cpp run ok
#include <stdexcept>
int count_until_throw(int n) {
  int i = 0;
  for (; i < n; ++i) {
    try {
      if (i == 3) throw std::runtime_error("stop");
    } catch (...) {
      break;    // OK: the handler is enclosed by the try-block, which is enclosed by the for
    }
  }
  return i;
}
int main() { return count_until_throw(10) == 3 ? 0 : 1; }
```

## Conditions (¶4–¶8)

The rules for conditions in the parentheses of `if`, `switch`, `while` and `for` are all here (¶4). The parentheses of `do` can only hold an expression ([[stmt.do]]).

### Expression or declaration (¶4, ¶7)

A condition can be an expression, or it can declare a variable:

```cpp run ok
int* get() { static int v; return &v; }
int main() {
  if (int* p = get()) { *p = 1; }    // = initialization
  if (int n{3}) { (void)n; }         // brace initialization
  if (const int k = 4) { (void)k; }  // const is a type specifier
}
```

A condition declaration accepts only `= expression` or a brace initializer, not a parenthesized initializer. The parenthesized form would produce even more ambiguities with function declarations and function-style casts in this position.

<div class="compare" markdown="1">

```cpp run ok
void g() {
  if (int n{3}) { (void)n; }
}
```

```cpp run error
void g() {
  if (int n(3)) { }  // error
}
```

</div>

¶4 also specifies that the declarator of a condition declaration shall not declare a function or an array, and the specifier sequence shall not define a class or enumeration. An array would decay to a non-null pointer and always be true as a condition; a function declaration has no initializer. Defining a type in a condition would bring a new class scope into an expression position, needlessly complicating parsing and scope rules. If `auto` appears, the type is deduced from the initializer per [[dcl.spec.auto]].

```cpp run error
void f() {
  if (int a[2] = {1, 2}) { }   // error: declares an array
  if (struct B { explicit operator bool() const { return true; } } b{}) { }
                               // error: defines a class in a condition
}
```

¶7 If a condition can be syntactically read both as an expression and as a condition declaration, it is treated as a declaration. This goes the same direction as the handling of statement-level ambiguity in [[stmt.ambig]].

```cpp run ok
struct T {
  int v;
  T(int x) : v(x) {}
  explicit operator bool() const { return v != 0; }
};
int x = 0;
int main() {
  // could be read as assigning 5 to the temporary T(x), or as declaring T x = 5.
  // By ¶7 it is a declaration: a new local variable x hides the global x.
  if (T(x) = 5) {
    return x.v == 5 ? 0 : 1;   // this x has type T
  }
  return 1;
}
```

Clang gives a `-Wvexing-parse` warning for this, explaining that the parentheses were taken as redundant parentheses around a declarator.

### The decision variable and the value of a condition (¶5–¶6)

¶5 The variable tested in a declaration-form condition is called the [[g:decision-variable|decision variable]]. In an ordinary condition declaration, the decision variable is the declared variable; for the structured binding form, the decision variable is specified by [[dcl.struct.bind]] as the underlying unnamed object *e*.

¶6 In statements other than `switch`, the value of a condition is the result of contextually converting the decision variable (or the expression) to `bool` ([[conv]]); if that conversion is ill-formed, the program is ill-formed. The condition of a `switch` is not converted to `bool` but to an integral or enumeration type per [[stmt.switch#2]].

A contextual conversion may use an `explicit operator bool`. `if (auto p = make())` testing a `std::unique_ptr`, and `while (std::cin >> x)` testing a stream, both rely on this:

```cpp run ok
#include <memory>
std::unique_ptr<int> make(bool b) {
  return b ? std::make_unique<int>(7) : nullptr;
}
int main() {
  if (auto p = make(true)) {   // operator bool is explicit; this is a contextual conversion
    return *p == 7 ? 0 : 1;
  }
  return 1;
}
```

### Structured bindings as conditions {{c++26}}

Before C++26, a condition could not be a structured binding; you had to bind in the *init-statement* first and then write the condition:

```cpp
if (auto [ptr, ec] = std::from_chars(b, e, v); ec == std::errc{}) { … }
```

[[P0963R3]] allows a structured binding declaration to be used directly as a condition. What is tested is the decision variable, that is, the whole bound object *e*, not any one binding. So this form is valid only if *e* itself can be contextually converted to `bool`. For exactly this purpose, `std::from_chars_result` gained an `operator bool` in C++26, which checks `ec == std::errc{}`.

```cpp run ok
#include <charconv>
int parse(const char* s, int len) {
  int v = 0;
  if (auto [ptr, ec] = std::from_chars(s, s + len, v)) {  // tests the from_chars_result
    (void)ptr; (void)ec;
    return v;
  }
  return -1;
}
int main() { return parse("42", 2) == 42 ? 0 : 1; }
```

<div class="compare" markdown="1">

```cpp run ok
struct P {
  int a, b;
  explicit operator bool() const {
    return a != 0;
  }
};
int f(P p) {
  if (auto [x, y] = p)  // tests the copy of P
    return x + y;
  return 0;
}
```

```cpp run error
#include <tuple>
void g(std::tuple<int, int> t) {
  // a tuple cannot be converted to bool
  if (auto [a, b] = t) { }  // error
}
```

</div>

For tuple-like types there is also an ordering guarantee: *e* is initialized and its conversion to `bool` completed first, and only then are the bindings initialized, that is, `get<i>` called ([[dcl.struct.bind#7]]). A type can therefore check in `operator bool` whether it holds a value, and let `get` be called only when it does.

### Permitted specifiers (¶8)

¶8 In a condition and in a *for-range-declaration* (including the structured binding declarations in them), each decl-specifier shall be either a type specifier or `constexpr`. `const`, `volatile`, `auto` and type names are type specifiers and can be used; `static`, `thread_local`, `extern`, `inline`, `constinit` and `typedef` cannot.

<div class="compare" markdown="1">

```cpp run ok
void f() {
  if (constexpr int n = 2) { (void)n; }
  for (const auto& c : "abc")
    (void)c;
}
```

```cpp run error
void g() {
  if (static int n = 1) { }
  for (static int i : {1, 2})
    (void)i;
}
```

</div>

!!! note "The scope of names declared in a condition"
    A name declared in a condition is in scope from its point of declaration to the end of the whole statement, `else` branch included. It cannot be redeclared in the outermost block of a substatement ([[basic.scope.block]]). Selection statements, iteration statements and their substatements each have their own block scope ([[stmt.select.general#2]], [[stmt.iter.general#2]]).

```cpp run error
void f(int* q) {
  if (int* p = q) {
    int p = 0;    // error: conflicts with p in the condition
  } else {
    int* p = q;   // error: the else branch too
  }
}
```

## Labels [stmt.label]

### Three kinds of labels (¶1)

¶1 There are three kinds of labels: identifier labels `name:`, `case constant-expression:` and `default:`. Any of them may be preceded by attributes, which appertain to the label rather than to the labeled statement.

The only use of an identifier label is as the target of `goto`. A function cannot have two labels with the same name; the scope is the whole function, not the block. A `goto` can be written before its label.

<div class="compare" markdown="1">

```cpp run error
void f(int n) {
  { L: ++n; }
  { L: --n; }   // error: duplicate label
  goto L;
}
```

```cpp run ok
void f() {
  int x = 0;
x:              // a label does not conflict with a variable
  if (++x < 3) goto x;
}
```

</div>

Labels and other names do not interfere with each other, so a label `x` can have the same name as a variable `x`.

### Labels at the end of a block {{c++23}}

The first sentence of ¶1 says that a label can be added to a statement or used anywhere in a compound statement. Together with the grammar of [[stmt.block]], `{ statement-seq(opt) label-seq(opt) }`, a block can end with a sequence of labels, treated as if followed by a null statement. Before C++23 a label had to label some statement, so people wrote `end: ;`. This change ([[P2324R2]]) matches C23.

```cpp run ok
void g(int n) {
  if (n < 0) goto out;
  switch (n) {
  case 1:
    ++n;
  default:        // OK since C++23: default is at the end of a block, no ; needed after it
  }
out:
}                 // OK since C++23: a label at the end of a block
```

### case and default must be enclosed by a switch (¶2)

¶2 A statement with a `case` or `default` label must be enclosed by some `switch` (as defined in ¶3 above). A lambda body is not a substatement, so a lambda inside a `switch` cannot contain a `case`:

```cpp run error
void f(int n) {
  switch (n) {
  case 0:
    [] {
    case 1: ;     // error: not enclosed by a switch
    }();
  }
}
```

### Control-flow-limited statements (¶3)

¶3 A [[g:control-flow-limited-statement|control-flow-limited statement]] S satisfies two conditions:

- ¶3.1 a `case` or `default` label appearing in S must be associated with a `switch` within S;
- ¶3.2 a label declared in S can only be referred to by a statement in S.

That is, control cannot enter S from outside, neither by `goto` nor by dispatch from an outer `switch`. The following statements are control-flow-limited:

- each substatement of `if constexpr` ([[stmt.if#2]]): a discarded branch may not be instantiated at all, so jumping into it makes no sense;
- each substatement of `if consteval` ([[stmt.if#5]]): one branch is for compile time and one for run time, and jumping in would bypass the choice between them;
- the compound statement of an expansion statement ([[stmt.expand#2]]): it is replicated several times, so there is no telling which copy a jump would target.

<div class="compare" markdown="1">

```cpp run error
void g() {
  goto inside;   // error
  if constexpr (true) {
  inside: ;
  }
}
```

```cpp run ok
void h(int n) {
  if constexpr (sizeof(int) == 4) {
    if (n) goto out;   // OK: jumping out
  }
out:;
}
```

</div>

The same goes for `switch`: a `case` written in an `if constexpr` branch inside a `switch` is also ill-formed.

### No identifier labels in expansion statements (¶4) {{c++26}}

¶4 An identifier label shall not be enclosed by an expansion statement, not even when both the `goto` and the label are inside the body of the expansion statement. The body is instantiated once per element, so the same label would appear several times, violating the rule that labels in one function must not repeat. `case` and `default` labels are not subject to this restriction, as long as the `switch` they belong to is also inside the body.

```cpp run error
void f() {
  template for (auto x : {1, 2}) {
    (void)x;
  again:          // error: an identifier label enclosed by an expansion statement
    ;
  }
}
```

## Expression statements [stmt.expr]

¶1 An expression statement has the form `expression(opt) ;`.

- Its expression is a [[g:discarded-value-expression|discarded-value expression]] ([[expr.context]]): the result is discarded. Only for a few simple forms of volatile glvalue is the lvalue-to-rvalue conversion applied. So `reg;` performs a read of a volatile variable, while `plain;` on an ordinary variable does nothing.
- All side effects of an expression statement are completed before the next statement is executed.
- A `;` with the expression omitted is called a **null statement**; it is often used as an empty loop body, and it is what `[[fallthrough]];` is attached to.

```cpp run ok
volatile int reg = 0;
int plain = 0;
int main() {
  reg;          // performs one volatile read
  plain;        // does nothing (Clang warns that the result is unused)
  (void)plain;  // explicitly discarded, no more warning
  ;             // null statement
}
```

The `[[nodiscard]]` warning ([[dcl.attr.nodiscard]]) targets function calls used as discarded-value expressions, and the expression statement `f();` is the most common case. Casting to `void` is the standard way to say that discarding the result is intentional.

## Compound statements [stmt.block]

¶1 A **compound statement** (also called a block) groups a sequence of statements into one statement: `{ statement-seq(opt) label-seq(opt) }`. For the labels at the end, see above.

The note in ¶2 points out that a compound statement defines a block scope ([[basic.scope.block]]). On leaving the block, automatic variables already constructed in it are destroyed in reverse order of construction ([[stmt.dcl]]).

```cpp run ok
#include <cstdio>
struct Tr { const char* n; ~Tr() { std::printf("~%s\n", n); } };
int main() {
  Tr a{"a"};
  {
    Tr b{"b"};
    Tr c{"c"};
  }             // prints ~c ~b
  Tr d{"d"};
}               // prints ~d ~a
```

## Common misconceptions

!!! pitfall "`if (x = 0)` is a comparison"
    It is an assignment, and the value of the condition is 0, that is, false. This is a common source of bugs in C-family languages; compilers usually warn about assignments in conditions, and an extra pair of parentheses, `if ((x = 0))`, marks it as intentional. `if (int x = 0)`, on the other hand, is a declaration and cannot be confused with a comparison.

!!! pitfall "A return inside a lambda can return from the enclosing function"
    It cannot. `break`, `continue`, `case`, `goto` and `return` do not cross a lambda body; a `return` inside a lambda only returns from the lambda. To make the enclosing function return, pass a signal through the return value.

!!! pitfall "`if (auto [ok, value] = f())` tests `ok`"
    It tests the whole bound object. To test one member, still use an *init-statement*: `if (auto [ok, v] = f(); ok)`.

## Questions

!!! question "Question 1"
    How many variables does the condition below declare?

    ```cpp
    struct T { T(int); explicit operator bool() const; };
    int a = 1;
    void f() { while (T(a) = 2) { } }
    ```

<details markdown="1">
<summary>Answer</summary>

One: `T a = 2`. By ¶7, a condition that can be read both as an expression and as a declaration is treated as a declaration, and the parentheses in `T(a)` are redundant parentheses around the declarator. Each iteration constructs a new local `a`, tests it, and destroys it at the end of that iteration ([[stmt.while#2]]). The global `a` is never used. Clang gives a `-Wvexing-parse` warning for this line.
</details>

!!! question "Question 2"
    Can a fallthrough statement be written in a lambda body inside a `switch`?

    ```cpp
    void f(int n) {
      switch (n) {
      case 0: [] { [[fallthrough]]; }();
      case 1: ;
      }
    }
    ```

<details markdown="1">
<summary>Answer</summary>

No. [[dcl.attr.fallthrough#1]] requires a fallthrough statement to appear within an enclosing `switch`. Enclosure is built on substatements, and a lambda body is not a substatement (Note 1 in ¶2), so this `switch` does not enclose the fallthrough statement in the lambda body, and the program is ill-formed. Clang reports "fallthrough annotation is outside switch statement".
</details>

!!! question "Question 3"
    Why is `if (auto [a, b] = std::pair{1, 2})` ill-formed while `if (auto [p, ec] = std::from_chars(…))` is valid?

<details markdown="1">
<summary>Answer</summary>

The value of a structured binding condition is the result of contextually converting the decision variable *e* (the whole object) to `bool` (¶5, ¶6). `std::pair<int, int>` has no conversion to `bool`, so the conversion is ill-formed and so is the program. `std::from_chars_result` has an `operator bool` in C++26, so it is valid. The bindings `a`, `b` or `p`, `ec` themselves never take part in the test.
</details>
