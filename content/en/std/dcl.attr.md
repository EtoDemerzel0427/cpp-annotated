---
title: Attributes
summary: "How attributes [[...]] are written, which entity or statement they appertain to, why unknown attributes are ignored, why removing standard attributes doesn't affect correctness, and deprecated, fallthrough, maybe_unused, likely, noreturn, indeterminate and C++26 annotations."
updated: 2026-10-19
---

!!! tldr
    - An attribute appertains to whatever its position says: at the start of a declaration, to the declared entity; after a name, to that name; before a statement, to that statement.
    - Attributes the compiler doesn't recognize are ignored, so one piece of code can carry several vendors' attributes at once; a misspelled standard attribute is silently ignored too.
    - Standard attributes only provide information that can be ignored: removing them gives the program no new behavior. A `[[noreturn]]` function returning, or an `[[assume]]` condition being false, is undefined behavior.
    - Two adjacent `[` can only open an attribute; `a[[] { return 0; }()]` is wrong even with a space in between.
    - C++26 annotations `[[=expr]]` are not hints for the compiler but constants attached to declarations, read by static reflection.

## What attributes are

```cpp
__attribute__((noreturn)) void die1();   // GCC and Clang spelling
__declspec(noreturn) void die2();        // MSVC spelling
[[noreturn]] void die3();                // standard spelling, since C++11
```

An **attribute** attaches an extra piece of information to a declaration, statement or type, such as "this function doesn't return", "this return value shouldn't be discarded" or "this branch rarely executes". Before C++11 every compiler had its own spelling. C++11 introduced the uniform `[[...]]` syntax, made the most common pieces of information standard attributes, and left namespaced room for vendor attributes such as `[[gnu::...]]`, `[[clang::...]]` and `[[msvc::...]]`.

¶1 The standard puts attributes and C++26 **annotations** (see below) in the same syntax, describing both as information attached to types, variables, names, contract assertions, blocks and even translation units. `alignas(...)` ([[dcl.align]]) is syntactically also an *attribute-specifier*, so it can appear in the same positions as attributes.

One `[[...]]` is an *attribute-specifier*, containing a comma-separated list of attributes. Each attribute consists of an **attribute-token** and an optional parenthesized argument; the token can be namespaced:

```text
[[ noreturn ]]                       attribute-token noreturn, no argument
[[ deprecated("use g2") ]]           with an argument
[[ gnu::always_inline, gnu::hot ]]   two namespaced vendor attributes
[[ using gnu: always_inline, hot ]]  same as above, without repeating the namespace
[[ =42 ]]                            C++26 annotation
```

## It appertains to whatever its position says (¶7)

```cpp run ok
[[nodiscard]] int f1();        // start of the declaration: appertains to the declared entity f1
int f2 [[nodiscard]] ();       // right after the name: appertains to f2
struct [[deprecated]] S {};    // after the class-key: appertains to the class S
enum E { a [[deprecated]] };   // after an enumerator: appertains to the enumerator a
void g(int n) {
  if (n) [[unlikely]] { }      // before a statement: appertains to that statement
}
int main() {}
```

¶7 Each attribute sequence **appertains to** some entity or statement, determined entirely by its syntactic position; the specific rules are scattered across [[stmt.pre]], [[dcl.pre]], [[dcl.meaning]] and elsewhere. If an attribute in the sequence isn't allowed to apply to what it appertains to, the program is ill-formed: `[[noreturn]] int a;` must be diagnosed, because `noreturn` only applies to functions.

The position rule is most easily gotten wrong with `if`. In `if (c) [[likely]] stmt;`, the attribute appertains to the then-branch statement; writing `if ([[likely]] c)` is a syntax error, because attributes can't go before the condition expression.

¶7 has two more restrictions. An attribute sequence appertaining to a friend declaration requires that friend declaration to be a definition; and attributes can't appertain to an explicit instantiation (Note 4, [[temp.explicit]]).

<div class="compare" markdown="1">

```cpp error
struct S1 {
  [[deprecated]]
  friend void fr1();  // error: not a definition
};
```

```cpp ok
struct S2 {
  [[nodiscard]]
  friend int fr2(S2) { return 1; }  // OK
};
```

</div>

A non-defining friend declaration may be the first declaration of the function, hidden inside some class. If it were allowed to carry attributes, different classes could give the same function contradictory attributes.

## Syntax details (¶2–¶6)

¶2 The `using` prefix (C++17, [[P0028R4]]) treats every following attribute-token as if prefixed with `N::`. Vendor attributes often come in groups, and this saves repeating the namespace. Once the prefix is used, namespaced tokens can't appear in the list:

```cpp run error
[[using CC: opt(1), debug]]   // same as [[CC::opt(1), CC::debug]]
  void f() {}
[[using CC: CC::opt(1)]]      // error: CC:: can't follow a using prefix
  void h() {}
```

`CC` is a made-up namespace, and Clang warns that the two attributes on `f` are unknown and ignored.

¶4 lists a few miscellaneous rules:

- Forms with no attributes, like `[[]]` and `[[,]]`, have no effect; the order of attributes in a list doesn't matter.
- Keywords appearing in an attribute-token are treated as ordinary identifiers, so vendors can define attributes like `[[gnu::const]]`.
- Attribute-tokens are not subject to name lookup. The `noreturn` in `[[noreturn]]` is not a declared name and has nothing to do with whether anything named `noreturn` is in scope.
- An `...` after an attribute is a pack expansion, but it can only be written if that attribute's specification allows it; no standard attribute does. ¶6 says an `...` after an annotation is also a pack expansion.
- The argument in parentheses is any sequence of tokens with balanced brackets, its form specified by each attribute (¶3). This lets vendor attributes have arbitrarily complex arguments.

¶5 is a note: unless otherwise specified, the attribute-tokens specified by the standard can't be used as macro names ([[cpp.replace.general]]). `#define noreturn` would break every `[[noreturn]]`.

## Unknown attributes are ignored (¶8)

```cpp run ok
[[gnu::always_inline, msvc::forceinline]]
inline int add(int a, int b) { return a + b; }

[[unknown_attr]] int x;   // ignored; Clang warns

int main() { return add(0, 0) + x; }
```

¶8 The behavior of attribute-tokens not specified by the standard is implementation-defined; tokens the implementation doesn't recognize are ignored. So the code above compiles on GCC, Clang and MSVC, each paying attention only to its own attributes. C++11 originally allowed implementations to reject unknown attributes; C++17's [[P0283R2]] changed this to "must ignore".

The price of ignoring is that typos are swallowed too: `[[nodicard]]`, missing an s, isn't an error; the compiler only gives a `-Wunknown-attributes` (Clang) or `-Wattributes` (GCC) warning.

Standard attributes are different. Note 5 points out that if a standard attribute is applied to something it isn't allowed on, or its arguments don't match its syntax, the program is ill-formed. So `[[noreturn]] int a;` must be diagnosed, while what happens with `[[vendor::noreturn]] int a;` is up to the vendor.

### Reserved names (¶8.1–¶8.2)

The following two kinds of attribute-tokens are reserved for future standardization; don't name your own attributes this way:

- ¶8.1 tokens without a namespace that the standard doesn't specify, such as `[[my_attr]]`. Your own attribute should be written `[[mycompany::my_attr]]`.
- ¶8.2 tokens whose namespace is `std` followed by zero or more digits, such as `[[std::x]]` and `[[std23::x]]`.

The standard also recommends that each implementation choose a distinctive name for its attribute namespace, such as `gnu`, `clang` or `msvc`.

## Removing standard attributes produces no new behavior (¶8 Note 6)

!!! std
    The *attribute*s specified in [dcl.attr] have optional semantics: given a well-formed program, removing all instances of any one of those *attribute*s results in a program whose set of possible executions ([intro.abstract]) for a given input is a subset of those of the original program for the same input…

Removing all instances of one standard attribute from a well-formed program gives a program whose possible executions for the same input are a subset of the original program's (disregarding any additional guarantees the implementation makes about that attribute). In other words, removing a standard attribute can only make behavior more determinate; nothing that was impossible before can happen. Taking them one by one:

| Attribute removed | Original program | After removal |
|---|---|---|
| `nodiscard`, `deprecated`, `maybe_unused`, `fallthrough`, `likely` | Only affects warnings and optimization | Possible executions unchanged |
| `assume(e)` | UB when `e` is false, so any execution is possible | Executes normally, a subset |
| `noreturn` | The function returning is UB | Returns normally, a subset |
| `indeterminate` | Reading an uninitialized variable is UB | Becomes erroneous behavior, a subset |
| `no_unique_address` | Layout may change | Layout was implementation-determined anyway; the new layout is within what's allowed |

The practical significance of this rule: standard attributes can't be used to change a program's meaning, and features that really affect semantics need their own syntax. It only constrains standard attributes. Vendor attributes can change semantics arbitrarily; for example `[[gnu::packed]]` changes layout and `[[clang::trivial_abi]]` changes the calling convention.

## `[[` can only open an attribute (¶9)

```cpp run error
void f() {
  int y[5];
  y[[] { return 2; }()] = 2;     // error: [[ can only open an attribute
  y[ [] { return 2; }()] = 2;    // error: a space doesn't separate the two [
  y[([] { return 2; })()] = 2;   // OK: separated by parentheses
  int i [[vendor::attr([[]])]];  // OK: [[ can appear inside an attribute argument
  (void)i;
}
```

¶9 Two consecutive `[` tokens can only appear in two places: opening an *attribute-specifier*, or inside an attribute argument. Note 7 adds that the program is ill-formed even if no attribute is allowed in that position, or the two brackets could have matched under another grammar.

The rule is about tokens, so whitespace in between doesn't matter. Attributes can appear in so many places that deciding from context whether `[[` is an attribute or a lambda inside a subscript could require arbitrarily long lookahead. The standard simply cuts it off at this level. To put a lambda in a subscript, wrap it in parentheses.

## Standard attributes at a glance

`__has_cpp_attribute(name)` detects at preprocessing time whether an attribute is supported ([[cpp.cond#5]]). For standard attributes the result is 0 or the value in the table below. The recommended practice for each attribute says that an implementation that doesn't actually make use of the attribute (giving no warnings and doing no optimization) should return 0.

| Attribute | Applies to | Effect | Introduced | `__has_cpp_attribute` |
|---|---|---|---|---|
| `alignas` | Variables, data members, classes | Alignment requirement, see [[dcl.align]] | C++11 | Not an attribute-token |
| `assume(expr)` | Null statements | Optimization assumption, see [[dcl.attr.assume]] | C++23 | 202207 |
| `deprecated("msg")` | Classes, aliases, variables, functions, namespaces, enumerations, enumerators, concepts, etc. | Warning on use | C++14 | 201309 |
| `fallthrough` | Null statements | Marks an intentional case fallthrough | C++17 | 201603 |
| `indeterminate` | Automatic variables, function parameters | Opt out of erroneous values | C++26 | 202403 |
| `likely` / `unlikely` | Statements, labels | Branch probability hint | C++20 | 201803 |
| `maybe_unused` | Entities, structured bindings, labels | No unused warning | C++17 | 201603 |
| `nodiscard("msg")` | Functions, classes, enumerations, constructors | Warning when the result is discarded, see [[dcl.attr.nodiscard]] | C++17 | 201907 |
| `noreturn` | Functions | The function doesn't return | C++11 | 200809 |
| `no_unique_address` | Non-static data members | Allows overlapping other members, see [[dcl.attr.nouniqueaddr]] | C++20 | 201803 |

With Clang 23, all of these return the values in the table except `indeterminate`, which returns 0 (not yet implemented).

## deprecated: marking things no longer recommended

```cpp run ok
[[deprecated("use g2() instead")]] void g1();
void g2();
enum Mode { fast, safe, legacy [[deprecated]] };
namespace [[deprecated]] old_api { inline int v = 1; }

void use() {
  g2();                // OK
  g1();                // warning: use g2() instead
  Mode m = legacy;     // warning
  int x = old_api::v;  // warning
  (void)m; (void)x;
}
```

[dcl.attr.deprecated] ¶1 `deprecated` marks names or entities that can still be used but whose use is discouraged for some reason, such as interfaces that are obsolete or unsafe. The string in parentheses explains the reason or recommends a replacement.

¶2 It can be applied to classes, type aliases, variables, non-static data members, functions, namespaces, enumerations, enumerators, concepts and template specializations.

¶3 An entity can first be declared without the attribute and have it added in a later redeclaration; the reverse also works, but once an entity is marked deprecated, later redeclarations can't undo it. The reason strings given by different declarations may differ.

¶4 The standard recommends that when a program refers to the name or entity other than to declare it, after a declaration carrying the attribute, the implementation should issue a diagnostic including the reason string. Declarations and redeclarations themselves don't trigger warnings.

## fallthrough: intentional fallthrough

```cpp run error
void g(), h(), i();
void f(int n) {
  switch (n) {
  case 1:
  case 2:
    g();
    [[fallthrough]];          // OK: the next statement has case 3
  case 3:
    do {
      [[fallthrough]];        // error: the next statement is outside the loop
    } while (false);
  case 5:
    h();                      // unmarked fallthrough: may warn
  case 4:
    i();
    [[fallthrough]];          // error: no case label follows
  }
}
```

If a branch of a `switch` finishes without a `break`, execution continues into the next branch; this is called fallthrough. Fallthrough is often a forgotten `break`, so compilers warn about it (Clang's `-Wimplicit-fallthrough`). `[[fallthrough]];` declares that this fallthrough is intentional.

[dcl.attr.fallthrough] ¶1 `fallthrough` can only be applied to a null statement; such a statement is called a [[g:fallthrough-statement|fallthrough statement]]. It must satisfy:

- it is inside some `switch` statement ([[stmt.switch]]);
- the next statement that would be executed after it must have a `case` or `default` label of the same `switch`, or the program is ill-formed;
- if it is in a loop, that statement must also be part of the same execution of the loop body; it can't use the loop to reach the next label;
- {{c++26}} if it is in an expansion statement (`template for`, [[stmt.expand]]), the `switch` it belongs to must also be inside that expansion statement; it can't fall through from one expanded copy of the code into another.

`[[fallthrough]];` at the end of the last branch is a common mistake, sometimes written for uniform formatting, but no label follows it, so the program is ill-formed. Clang's diagnostic is `fallthrough annotation does not directly precede switch label`.

¶2 The standard recommends that a fallthrough statement suppress the fallthrough warning, and that implementations warn if a fallthrough statement can never be executed. Two adjacent labels with no statements in between (`case 1:` and `case 2:` above) don't get a warning anyway and need no marking.

## maybe_unused: intentionally unused

```cpp run ok
#include <cassert>
[[maybe_unused]] static void f([[maybe_unused]] bool thing1,
                               [[maybe_unused]] bool thing2) {
  [[maybe_unused]] bool b = thing1 && thing2;
  assert(b);               // b is unused when NDEBUG is defined
}
int main() {}
```

[dcl.attr.unused] ¶1 `maybe_unused` indicates that a name, label or entity may be intentionally unused, which is common for variables and functions used only in some build configurations.

¶2 It can be applied to classes, type aliases, variables, structured binding declarations or individual bindings in them, the result binding of a contract ([[dcl.contract.res]]), non-static data members, functions, enumerations, enumerators, and identifier labels ([[stmt.label]]). ¶3 It can be added in a later redeclaration and takes effect from the first declaration that has it.

¶4 The standard recommends that implementations not report whether entities and labels with this attribute are used or unused. For a structured binding declaration `auto [a, b] = ...;` without the attribute, a warning should be given only if none of the bindings is used. Unused warnings themselves aren't a concept in the standard, so this attribute's effect lies entirely in recommended practice.

## likely and unlikely: branch probability hints {{c++20}}

```cpp run ok
void g(int);
int f(int n) {
  if (n > 5) [[unlikely]] {   // n > 5 is assumed to be very rare
    g(0);
    return n * 2 + 1;
  }
  switch (n) {
  case 1:
    g(1);
    [[fallthrough]];
  [[likely]] case 2:          // n == 2 is assumed to be far more common than other values
    g(2);
    break;
  }
  return 3;
}
int main() {}
```

[dcl.attr.likelihood] ¶1 `likely` and `unlikely` apply to statements or labels, take no arguments, and can't both appear in the same attribute sequence.

¶2 is a note explaining the design intent: implementations can optimize for the case that paths of execution including `likely` are arbitrarily more likely than other paths, and the reverse for `unlikely`. Compilers usually turn them into branch weights, with an effect similar to `__builtin_expect`, except that they mark statements rather than expressions. Note 2 warns that overusing them can make performance worse.

A path of execution includes a label if and only if it contains a jump to that label. In the example above, the path falling through from `case 1` into `case 2` doesn't jump to `case 2`, so `[[likely]]` only describes the `switch` jumping directly to `case 2`.

## noreturn: the function doesn't return

```cpp run ub
[[noreturn]] void f() {
  throw "error";             // OK: throwing isn't returning
}
[[noreturn]] void q(int i) {
  if (i > 0)
    throw "positive";
}                            // returns when i <= 0
int main() {
  try { f(); } catch (...) {}
  try { q(0); } catch (...) {}   // UB: q returned
}
```

[dcl.attr.noreturn] ¶1 `noreturn` says a function does not return; it can be applied to functions and to lambda call operators (the latter since C++23, [[P2173R1]]). `std::abort`, `std::exit`, `std::terminate` and `std::unreachable` all have it.

Knowing a call won't return, the compiler can skip generating code after the call, treat the following code as unreachable, and stop warning about a missing `return`. So ¶1 requires that if any declaration has `noreturn`, the function's first declaration must have it; otherwise call sites seen earlier would already have been compiled assuming a return. If one translation unit has it and another doesn't, the program is ill-formed, no diagnostic required (IFNDR: the compiler need not report it and the program has no guarantees).

¶2 If a call to a `noreturn` function actually returns, the behavior is [[g:runtime-undefined-behavior|runtime-undefined]]: UB in ordinary execution; during constant evaluation, the implementation decides whether this makes the expression non-constant. Note 1 explains that throwing an exception isn't returning, so `noreturn` has nothing to do with `noexcept`.

¶3 The standard recommends that implementations warn when a function might return. For `q` above, Clang's warning is `function declared 'noreturn' should not return`.

## indeterminate: opting out of erroneous values {{c++26}}

```cpp
void f(int);
void g() {
  int x [[indeterminate]], y;
  f(y);   // erroneous behavior
  f(x);   // undefined behavior
}
```

C++26 changed reading an uninitialized automatic variable from UB to [[g:erroneous-behavior|erroneous behavior]] ([[basic.indet]], [[P2795R5]]): the variable gets an erroneous value chosen by the implementation, and reading it is an error but with a defined result, which the compiler can't assume doesn't happen. The cost is that the compiler may really have to write a value into each such variable. `[[indeterminate]]` turns this mechanism off for a single variable.

[dcl.attr.indet] ¶1 It can be applied to the definition of a block variable with automatic storage duration, or to a parameter in a function declaration, and takes no arguments. It makes the object's storage initially indeterminate rather than erroneous. So in the example above, reading `y` is erroneous behavior and reading `x` is undefined behavior (Note 1 in ¶3).

It also applies to parameters because a class-type parameter passed by value is a new automatic object. If its constructor doesn't initialize some member, that member gets an erroneous value in C++26. ¶2 requires this attribute on a parameter to appear on the function's first declaration; if one translation unit's first declaration has it and another's doesn't, the program is IFNDR.

It's only worth using when measurement shows the cost of writing erroneous values is unacceptable. The typical case is a large stack buffer that will be filled immediately, such as `char buf [[indeterminate]] [65536];` followed by a `read()`.

!!! impl "Implementation status"
    Clang 23 doesn't implement this attribute yet: `__has_cpp_attribute(indeterminate)` is 0, and `[[indeterminate]]` is ignored as an unknown attribute. By the ignorability rule above, that's allowed. GCC and Clang have long had `-ftrivial-auto-var-init=zero|pattern`, which writes an initial value into every automatic variable; Clang also has `[[clang::uninitialized]]` for opting out per variable.

## Annotations: data for reflection {{c++26}}

```cpp
struct [[=1]] S {};   // annotation: a constant with value 1
[[=2, =3, =2]] void g();
void g [[=4, =2]] ();  // g has 5 annotations in total
```

Annotations are a companion feature of C++26 static reflection ([[P3394R4]]). They attach a compile-time constant to a declaration, which the program then reads with `std::meta::annotations_of` ([[meta.reflection.annotation]]). Attributes are for the compiler; annotations are for the program itself. For example, a serialization library can read `[[=rename("id")]]` on a member to decide the output field name.

[dcl.attr.annotation] ¶1 An annotation can be applied to a base-specifier or to a declaration of a type, type alias, variable, function, function parameter of non-`void` type, namespace, enumerator or non-static data member. There are two exceptions: a declaration written at block scope that declares an entity of an enclosing namespace (such as `extern int x;` in a function body, where per ¶1.1 the host scope differs from the target scope), and a non-defining friend declaration; for function parameters, the containing function declaration is what's checked. An annotation on a parameter of a function definition appertains both to the function parameter and to the variable in the function body (Note 1).

¶2 The value of an annotation is the result of `std::meta::reflect_constant(expr)`, called the annotation's **underlying constant**, so `expr` must be a constant expression whose type can be a constant template argument (a [[g:structural-type|structural type]]).

¶3 Each annotation is a separate one, and identical values aren't merged. In the example above, the two declarations of `g` carry 5 annotations in total, so it has 5. Different instantiations of the same template each have their own annotations.

¶4 Substitution into an annotation is not in the immediate context, so a substitution failure in an annotation is a hard error, not something that just discards the candidate function as with SFINAE:

```cpp
template<class T>
  [[=T::type()]] void f(T t);
void f(int);

void g() {
  f(0);     // OK: the non-template f(int) wins
  f('0');   // error: the template is selected, and substituting into the annotation gives an invalid expression
}
```

An annotation is just data attached to a declaration, not part of the function signature, and shouldn't influence overload resolution.

!!! impl "Implementation status"
    Clang 23 (Homebrew, libc++) doesn't implement static reflection yet: `[[=1]]` can't be parsed and there's no `<meta>` header. The examples in this section are analyzed from the standard text and haven't been verified by compiling.

## History

!!! history
    - C++11: attribute syntax ([[N2761]]), `noreturn`, `carries_dependency`, `alignas`. How unknown attributes were handled was up to the implementation.
    - C++14: `deprecated`.
    - C++17: `fallthrough` ([[P0188R1]]), `nodiscard`, `maybe_unused` ([[P0212R1]]); the `using` prefix ([[P0028R4]]); unknown attributes must be ignored ([[P0283R2]]); namespaces and enumerators can have attributes.
    - C++20: `likely`/`unlikely` ([[P0479R5]]), `no_unique_address`; `nodiscard` can have a reason and can be applied to constructors.
    - C++23: `assume`; lambda call operators can have attributes ([[P2173R1]]); the same attribute can be repeated within one attribute list ([[P2156R1]]), as in `[[nodiscard, nodiscard]]`.
    - C++26: `indeterminate` ([[P2795R5]]); annotations ([[P3394R4]]); `carries_dependency` removed; strings in attribute arguments became unevaluated strings ([[P2361R6]]); the ignorability of standard attributes was reworded, and `__has_cpp_attribute` must return 0 when the implementation doesn't make use of an attribute ([[P2552R3]]); individual structured bindings can have attributes. The current draft also allows `maybe_unused` on labels.

## Common misconceptions

!!! pitfall "Attributes don't change semantics"
    This is only true for standard attributes. Vendor attributes can change layout, calling conventions and sizes; the ignorability rule only constrains the attributes specified in [dcl.attr].

!!! pitfall "`[[noreturn]]` means it doesn't throw"
    It only promises not to return; throwing is perfectly fine and is one of the usual ways a `noreturn` function ends.

## Questions

!!! question "Question 1"
    Is each line below ill-formed, or ignored?
    ```cpp
    [[noreturn]] int a;
    [[gnu::noreturn]] int b;
    [[nodiscard]] [[nodiscard]] int c();
    [[my_attr]] int d;
    [[std::my_attr]] int e;
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: ill-formed. `noreturn` only applies to functions (¶7, Note 5), and Clang reports an error.
- `b`: `gnu::noreturn` is a vendor attribute with implementation-defined behavior; the standard requires no diagnostic. Clang warns `'noreturn' only applies to function types` and ignores it.
- `c`: well-formed. Repeating the same attribute in two separate `[[...]]` has always been allowed; since C++23 writing it twice in the same list is allowed too.
- `d`: ignored. But an un-namespaced token not specified by the standard is reserved for the future (¶8.1) and shouldn't be used as a name.
- `e`: ignored; tokens in the `std` namespace are reserved too (¶8.2).
</details>

!!! question "Question 2"
    Why could `assume` be made a standard attribute, while C++26 contract assertions `pre(expr)` have their own syntax?

<details markdown="1">
<summary>Answer</summary>

Because of the ignorability rule (¶8 Note 6). Removing `[[assume(e)]]` turns the UB when `e` is false into a defined execution, so the possible executions can only shrink. A failed contract check may terminate the program; removing the assertion would let the program carry on, an execution impossible in the original program, so it's no longer a subset. So contracts can't be an ignorable attribute.
</details>
