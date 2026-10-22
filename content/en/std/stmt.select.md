---
title: "Selection statements: if, if constexpr, if consteval, switch"
summary: "How if and switch choose a branch: the forms with an initializer, the discarded statements of if constexpr, the immediate function context of if consteval, and the condition type, case constants and no-skipping-initialization rule of switch."
updated: 2026-10-19
---

!!! tldr
    - `if (init; cond)` and `switch (init; cond)` behave as if wrapped in another pair of braces; the variable in the initializer lives until the end of the whole statement and can be used in the `else` branch too.
    - When the condition of `if constexpr` is false, that branch is a discarded statement: inside a template it is not instantiated; outside a template it still has to pass every semantic check.
    - The first branch of `if consteval` is an immediate function context, so run-time arguments can be passed to `consteval` functions there; `if (std::is_constant_evaluated())` cannot do that.
    - The condition of `switch` undergoes integral promotion first, and every `case` constant is converted to the promoted type, with no narrowing allowed and no duplicates.
    - Going from the condition of a `switch` to a `case` label counts as a jump and cannot bypass a local variable with an initializer.

C++ has only two selection statements: `if` and `switch`. `if` later gained three variants, each solving a practical problem:

| Form | Introduced | Problem solved |
|---|---|---|
| `if (init; cond)`, `switch (init; cond)` | C++17 | A variable used only for the test gets a scope covering exactly this statement |
| `if constexpr (cond)` | C++17 | Inside a template, drop a branch according to a compile-time condition without instantiating it |
| `if consteval { }` | C++23 | Distinguish constant evaluation from run time, and call `consteval` functions in the compile-time branch |

The rules for the condition itself (declaration-form conditions, the decision variable, contextual conversion to `bool`) are in [[stmt.pre]].

## Each branch is a scope [stmt.select.general]

```cpp ok
void f(bool b) {
    if (b)
        int i = 1;   // i exists only in this branch
    else
        int i = 2;   // another i in another scope
}
```

¶1 Selection statements have five syntactic forms: `if` with or without `constexpr` and with or without `else`, `if consteval` with or without `!` and with or without `else`, and `switch`. The optional *init-statement* in the parentheses ends with its own semicolon, so the semicolon in `if (x; y)` belongs to the *init-statement* and is not a separator.

¶2 Each selection statement, and each of its substatements, has its own block scope ([[basic.scope.block]]). So a branch is a separate scope even if it is not a compound statement in braces. The two `i` above do not conflict, and neither is visible after the `if`.

The outer scope holds the names declared in the *init-statement* and the condition, so a variable declared in the condition cannot be redeclared in the outermost level of a branch (see [[stmt.pre]] for an example).

## Executing if [stmt.if]

¶1 If the condition is `true`, the first substatement is executed; if there is an `else` and the condition is `false`, the second substatement is executed.

When the first substatement is entered by jumping to a label, the condition is not evaluated and the `else` branch is not executed:

```cpp run ok
#include <cstdio>
int main() {
    int n = 0;
    goto in;
    if (++n > 100) {     // the condition is not evaluated; n stays 0
    in:
        std::puts("then");
    } else {
        std::puts("else");   // not executed
    }
    return n;            // 0
}
```

The same paragraph also resolves the dangling-else ambiguity: an `else` is associated with the nearest `if` that does not already have an `else`, regardless of indentation.

```cpp run ok
int sign(int a, int b) {
    if (a > 0)
        if (b > 0) return 1;
        else return 2;   // belongs to if (b > 0)
    return 3;
}
int main() { return sign(-1, 5) == 3 ? 0 : 1; }
```

Under `-Wall`, Clang gives a `-Wdangling-else` warning for this and suggests adding braces.

## if and switch with an initializer {{c++17}}

Before C++17, the pattern "get a value, test it, use it" could only leave the variable in the outer scope, or wrap it in a hand-written pair of braces. Now it can be written as:

```cpp run ok
#include <map>
#include <string>
std::map<std::string, int> table{{"a", 1}};
int lookup(const std::string& k) {
    if (auto it = table.find(k); it != table.end())
        return it->second;
    else
        return -static_cast<int>(table.size());
}   // it is visible in the else too, and not visible after leaving the if
int main() { return lookup("a") == 1 ? 0 : 1; }
```

¶3 `if (init-statement condition) ...` is equivalent to

```text
{
    init-statement
    if (condition) statement [else statement]
}
```

except for one point: the *init-statement* and the condition are in the same scope. Under the literal rewrite they would be in nested scopes, and the condition could redeclare a variable of the same name; under the real rule this is a redeclaration:

```cpp error
void f() {
    if (int x = 1; int x = 2) { }   // error: x redeclared
}
```

[[stmt.switch#7]] says the same for `switch`:

```cpp run ok
#include <cctype>
int classify(const char* s) {
    switch (char c = s[0];
            std::isdigit(static_cast<unsigned char>(c)) ? 1 : 0) {
    case 1:  return c - '0';
    default: return -1;
    }
}
int main() { return classify("7") == 7 ? 0 : 1; }
```

The *init-statement* can be an expression statement or a simple declaration, and since C++23 also an alias declaration:

```cpp ok
#include <vector>
int g(const std::vector<int>& v) {
    if (using T = std::vector<int>::size_type; T n = v.size())
        return static_cast<int>(n);
    return 0;
}
```

!!! pitfall "An unnamed lock_guard"
    In `if (std::lock_guard{m}; ready)`, `std::lock_guard{m};` is not a declaration but an expression statement: it creates a temporary that is destroyed at the semicolon, so the lock has already been released when `ready` is tested. Write `if (std::lock_guard lk{m}; ready)`.

## if constexpr {{c++17}}

### The condition

¶2 An `if` written as `if constexpr` is called a **constexpr if statement**. Its condition is first contextually converted to `bool`, and the converted expression must be a constant expression.

The order in the wording matters. C++17 required the condition to be a contextually converted constant expression of type `bool` ([[expr.const.const]]), and converted constant expressions do not allow narrowing; `unsigned` to `bool` is exactly a narrowing, so `if constexpr (flags & 4)` was originally ill-formed. [[P1401R5]] in C++23 changed it to the current wording, which allows narrowing:

```cpp ok
constexpr unsigned flags = 4;
void f() {
    if constexpr (flags & 4) { }        // unsigned → bool, OK since C++23
    if constexpr (sizeof(int[2])) { }   // Example 1 in the standard: size_t → bool
}
```

Clang 23 also accepts the first line under `-std=c++17`, without a diagnostic.

### Discarded statements

If the converted condition is `false`, the first substatement is a [[g:discarded-statement|discarded statement]]; otherwise the second substatement, if any, is a discarded statement.

This is most useful in templates. When the enclosing templated entity is instantiated, if the condition is no longer value-dependent, the discarded statement is not instantiated:

```cpp run ok
#include <string>
#include <type_traits>
template<class T>
std::string to_str(const T& t) {
    if constexpr (std::is_arithmetic_v<T>)
        return std::to_string(t);   // not instantiated for T = std::string
    else
        return std::string(t);      // not instantiated for T = int
}
int main() {
    return to_str(42) == "42" && to_str(std::string("x")) == "x" ? 0 : 1;
}
```

Each branch is valid only for some `T`. Without `if constexpr`, this needed two overloads plus SFINAE or tag dispatch. Recursion over variadic templates also no longer needs a separate terminating overload (the first half of Example 2 in the standard):

```cpp run ok
#include <cstdio>
void handle(int v) { std::printf("%d\n", v); }
template<typename T, typename... Rest>
void g(T&& p, Rest&&... rs) {
    handle(p);
    if constexpr (sizeof...(rs) > 0)
        g(rs...);       // never instantiated for an empty pack
}
int main() { g(1, 2, 3); }
```

### Outside templates: checked as usual

Outside a template there is no instantiation, and a discarded statement still has to pass every semantic check, including name lookup and type checking. `if constexpr` is not the preprocessor's `#if`.

<div class="compare" markdown="1">

```cpp error
void g() {
    if constexpr (false) {
        undeclared();  // error: undeclared
    }
}
```

```cpp error
void q() {
    if constexpr (true) { }
    else { int* p = 1.0; } // error
}
```

</div>

Two effects, however, hold outside templates as well:

- An odr-use (the kind of use that requires the entity to be defined, see [[basic.def.odr]]) in a discarded statement does not require the used entity to be defined (Note 1 in ¶2).
- A `return` in a discarded statement does not take part in return type deduction ([[dcl.spec.auto#4]]).

```cpp run ok
#include <type_traits>
extern int x;                  // not defined
int f() {
    if constexpr (true)
        return 0;
    else if (x)                // odr-uses x in a discarded statement: no definition needed
        return x;
    else
        return -x;
}
auto h() {
    if constexpr (true) return 1;
    else return 2.0;           // does not take part in deduction
}
static_assert(std::is_same_v<decltype(h()), int>);
int main() { return f(); }
```

`f` is the second half of Example 2 in the standard. The `if` in `else if (x)` is an ordinary `if`, and the whole `if (x) ... else ...` is inside the discarded statement.

| Effect | Basis | Inside a template | Outside a template |
|---|---|---|---|
| Not instantiated | [[stmt.if#2]] | Yes (when the condition is not value-dependent after instantiation) | Not applicable; checked as usual |
| odr-use does not require a definition | [[stmt.if#2]] Note 1 | Yes | Yes |
| `return` does not take part in deduction | [[dcl.spec.auto#4]] | Yes | Yes |

### static_assert(false) in templates {{c++23}}

Not instantiated does not mean not checked. A discarded branch in a template is still parsed, and errors that do not depend on template parameters are usually reported at the definition. Under [[temp.res.general#6]], if no valid specialization could be generated for a substatement of a constexpr if, the program is ill-formed, no diagnostic required.

This rule used to keep `static_assert(false, ...)` out of discarded branches. [[P2593R1]] in C++23 made [[temp.res.general#6]] ignore failed `static_assert`s and specified that a `static_assert` in a template fails only when instantiated, so it can now be written directly:

```cpp ok
#include <type_traits>
template<class T>
int code(T) {
    if constexpr (std::is_integral_v<T>)
        return 1;
    else
        static_assert(false, "unsupported type");   // fires only if the else is instantiated
}
int a = code(1);
```

Before that, the workaround was a condition that depends on `T`, such as `static_assert(sizeof(T) == 0)`. Outside templates there is no such protection, and `static_assert(false)` in a discarded statement fires anyway:

```cpp error
void h3() {
    if constexpr (false) { static_assert(false); }   // error
}
```

!!! lawyer "The condition is still value-dependent after the outer instantiation"
    If an `if constexpr` is in a generic lambda and its condition depends on the type of the lambda's own parameter, the condition is still value-dependent when the outer template is instantiated, and both branches are kept. Only when the lambda's `operator()` is instantiated is the discarded one dropped:

    ```cpp
    template<class T> void outer(T) {
        [](auto u) {
            if constexpr (sizeof(u) > 100) u.nonexistent();
        }(0);                  // u is int: only now is that branch discarded
    }
    template void outer(int);  // OK
    ```

### No jumping into a branch

The last sentence of ¶2 specifies that each substatement of a constexpr if is a [[g:control-flow-limited-statement|control-flow-limited statement]] ([[stmt.label#3]]): it cannot be entered from outside by `goto`, and `case` labels of an outer `switch` cannot be placed in it. Otherwise a branch that might not exist could become a jump target. See [[stmt.pre]] for examples.

!!! pitfall "`else if` does not automatically become `else if constexpr`"
    ```cpp
    if constexpr (A) { ... }
    else if (B) { ... }            // an ordinary if: both branches are instantiated
    else if constexpr (B) { ... }  // this is the compile-time choice
    ```

!!! pitfall "`if constexpr (std::is_constant_evaluated())` is always true"
    The condition of `if constexpr` is itself [[g:manifestly-constant-evaluated|manifestly constant-evaluated]] ([[expr.const.defns]]), so `std::is_constant_evaluated()` there is always `true`. Clang gives a `-Wconstant-evaluated` warning for this. Use `if consteval`, or an ordinary `if (std::is_constant_evaluated())`.

!!! note "Coroutines"
    A `return` statement cannot appear in a coroutine, not even in a discarded statement (the note in [[stmt.return.coroutine#1]]). So `if constexpr` cannot be used to conditionally keep an ordinary `return` in a coroutine.

## if consteval {{c++23}}

```cpp run ok
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if consteval {
        return sq_ct(x);   // OK: even though x is not a constant
    } else {
        return x * x;      // run-time path
    }
}
static_assert(sq(3) == 9);   // takes the first branch
int main(int argc, char**) {
    return sq(argc) == 1 ? 0 : 1;   // takes the else
}
```

¶4 An `if` written as `if consteval` is called a **consteval if statement**. It has no condition and no *init-statement*, and its branches must be compound statements.

¶5 If a consteval if statement is evaluated in a context that is manifestly constant-evaluated (such as the condition of a `static_assert` or the initializer of a `constexpr` variable), the first substatement is executed; otherwise the `else` branch, if any, is executed. Both substatements are control-flow-limited statements.

The key is Note 2 in ¶5: the first substatement is an [[g:immediate-function-context|immediate function context]] ([[expr.const.imm]]). A `consteval` function is one that can only be called at compile time, and normally every call to it must itself be a constant expression; in an immediate function context that requirement does not apply. An ordinary `if (std::is_constant_evaluated())` does not have this effect:

```cpp error
#include <type_traits>
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if (std::is_constant_evaluated())
        return sq_ct(x);   // error: not an immediate function context, x is not a constant
    return x * x;
}
```

This also explains why `if consteval` was designed as a statement rather than a Boolean expression: being in an immediate function context is a property of a piece of code and has to be attached to the syntax; and whether evaluation is constant should not be a value that can be stored in a variable and passed around.

The braces are mandatory. Example 3 in the standard explains why: if the branches of `if consteval` could be arbitrary statements, dangling-else ambiguities would be even harder to spot.

```cpp error
constexpr int f(int x) {
    if consteval return x;   // error: must be a compound statement
    else return 0;
}
```

¶6 `if ! consteval { A }` is not a consteval if statement but is equivalent to `if consteval { } else { A }`; `if ! consteval { A } else B` is equivalent to `if consteval B else { A }`. So the first branch of `if !consteval` is not an immediate function context; its `else` branch is.

```cpp error
consteval int sq_ct(int x) { return x * x; }
constexpr int h(int x) {
    if !consteval { return -1; }
    return sq_ct(x);   // error: this is not an immediate function context
}
```

## switch [stmt.switch]

### The condition and case constants

```cpp error
void f(unsigned u, unsigned char c, int i) {
    switch (u) { case -1: break; }   // error: narrowing
    switch (c) { case 300: break; }  // OK: c is promoted to int
    switch (i) { case 1.0: break; }  // error: double → int
    switch (i) { case 'a': case 97: break; } // error: duplicate
}
```

¶1–¶2 `switch` transfers control to one of several statements depending on the value of the condition. The value of the condition is determined in these steps:

1. If the condition is an expression, its value is taken; if it is a declaration, the value of the decision variable is taken ([[stmt.pre#5]]). There is no conversion to `bool` here.
2. The value must be of integral, enumeration or class type. A class type is contextually implicitly converted to an integral or enumeration type, which requires the class to have exactly one suitable non-explicit conversion function.
3. If the resulting type is subject to integral promotion, it is converted to the promoted type; for example, `unsigned char`, `short` and `bool` become `int`. The result is called the adjusted type of the condition.

The constant expression after each `case` must be a [[g:converted-constant-expression|converted constant expression]] of the adjusted type, so narrowing is not allowed, nor is a floating-point to integer conversion. Within one `switch`, no two converted case values may be equal. The four lines of the example above correspond to these rules.

There is no implicit conversion between scoped enumerations and integers, so the `case`s can only be enumerators:

```cpp error
enum class E { a, b };
void g(E e) {
    switch (e) {
    case E::a: break;   // OK
    case 0: break;      // error: int cannot be implicitly converted to E
    }
}
```

A condition of class type:

```cpp ok
struct Code {
    int v;
    operator int() const { return v; }
};
int f(Code c) {
    switch (c) {   // contextually implicitly converted to int
    case 1: return 10;
    default: return 0;
    }
}
```

¶3 A `switch` has at most one `default:`. ¶4 `switch` statements can be nested; a `case` or `default` label belongs to the smallest `switch` enclosing it.

### Execution and fallthrough

¶5 When a `switch` is executed, the condition is evaluated first. If some case constant equals the condition, control jumps to that label; if none does, to `default`; if there is no `default` either, none of the statements in the `switch` is executed.

¶6 Labels themselves do not alter the flow of control: execution continues past the next `case` label, which is called falling through. To leave the `switch`, use `break` ([[stmt.break]]). When falling through is intentional, write `[[fallthrough]];` ([[dcl.attr.fallthrough]]) to silence the `-Wimplicit-fallthrough` warning.

`case` labels need not appear at the top level of the `switch` body, as long as they are enclosed by that `switch` ([[stmt.label#2]]). The best-known example is Duff's device, with labels inside the body of a `do` loop:

```cpp ok
void send(volatile short* to, const short* from, int count) {
    int n = (count + 7) / 8;
    switch (count % 8) {
    case 0: do { *to = *from++;
    case 7:      *to = *from++;
    case 6:      *to = *from++;
    case 5:      *to = *from++;
    case 4:      *to = *from++;
    case 3:      *to = *from++;
    case 2:      *to = *from++;
    case 1:      *to = *from++;
            } while (--n > 0);
    }
}
```

This does not work when a control-flow-limited statement (such as a branch of `if constexpr`) is in between.

### No skipping initialization

```cpp error
#include <string>
int f(int k) {
    switch (k) {
    case 0:
        std::string s = "zero";  // its scope extends to the end of the switch
        return 0;
    case 1:                      // error: bypasses the initialization of s
        return 1;
    }
    return -1;
}
```

Going from the condition to a `case` label counts as a jump, so [[stmt.dcl#2]] applies: a jump cannot pass a local variable's declaration into its scope unless the variable has [[g:vacuous-initialization|vacuous initialization]], that is, default-initialization that does nothing (such as `int x;`).

The fix is to give that case a pair of braces, confining the variable to its own block:

<div class="compare" markdown="1">

```cpp ok
#include <string>
int f(int k) {
    switch (k) {
    case 0: {
        std::string s = "zero";
        return (int)s.size();
    }
    case 1:
        return 1;
    }
    return -1;
}
```

```cpp ok
void g(int k) {
    switch (k) {
    case 0:
        int x;   // vacuous initialization
        x = 1;
        (void)x;
        break;
    case 1:
        x = 2;   // OK: just an assignment
        (void)x;
        break;
    }
}
```

</div>

## Implementation view

!!! impl "When if constexpr is checked"
    GCC, Clang and MSVC all parse both branches at the template definition, and substitute only into the chosen branch at instantiation. Errors in a discarded branch that depend on template parameters are never reported; obvious errors that do not depend on them are usually reported at the definition. The standard guarantees only that the branch is not instantiated, not that it is not checked, so the same discarded code may be diagnosed at different times by different compilers.

!!! impl "Code generation for switch"
    When the case values are dense, compilers usually generate a jump table, indexing it by the condition value to get the target address; when they are sparse, a comparison tree. GCC and Clang support range cases `case 1 ... 5:`, a GNU extension that is not standard C++. A `switch` on an enumeration that does not cover every enumerator and has no `default` triggers a warning from `-Wswitch` (in `-Wall`).

## History

!!! history
    - C++98 already had declaration-form conditions, class-type `switch` conditions, and the no-skipping-initialization rule.
    - C++17 added `if constexpr` ([[P0292R2]]), `if`/`switch` with an initializer ([[P0305R1]]) and `[[fallthrough]]`.
    - C++23 added `if consteval` ([[P1938R3]]), allowed the condition of `if constexpr` to narrow to `bool` ([[P1401R5]]), allowed the *init-statement* to be an alias declaration, and made `static_assert(false)` in uninstantiated templates valid ([[P2593R1]]).
    - C++26 allows the condition to be a structured binding declaration (see [[stmt.pre]]).

## Questions

!!! question "1. Is the program below well-formed? What is the return type of `f<int>`?"
    ```cpp
    template<class T> auto f() {
        if constexpr (sizeof(T) > 1) return 1;
        else return 'c';
    }
    auto x = f<int>();
    auto y = f<char>();
    ```

<details markdown="1">
<summary>Answer</summary>

Well-formed. In each specialization, the discarded `return` does not take part in return type deduction ([[dcl.spec.auto#4]]), and the discarded branch is not instantiated. `f<int>` returns `int` and `f<char>` returns `char`: different specializations of the same template can deduce different return types.
</details>

!!! question "2. What happens when `f(1)` is executed?"
    ```cpp
    int f(int k) {
        switch (k) {
            int x = 42;       // ①
        case 1:
            return x;
        }
        return 0;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

The program is ill-formed and never runs. Jumping from the condition to `case 1` enters the scope of `x` while bypassing its initialization, violating [[stmt.dcl#2]]. Changed to `int x;`, the program is well-formed, but `return x;` reads an uninitialized `int`: in C++26 this is erroneous behavior (an erroneous value is read, see [[basic.indet]]); before that it was undefined behavior.
</details>

!!! question "3. The first branch of `if consteval` calls an ordinary `constexpr` function, which passes a run-time argument on to a `consteval` function. Is that allowed?"

<details markdown="1">
<summary>Answer</summary>

No, unless that function gets promoted to an immediate function (for example, if it is a constexpr function template or a lambda, see [[expr.const.imm]]). The immediate function context covers only the code of the first branch of `if consteval` itself, not the functions it calls. In the called ordinary `constexpr` function, the `consteval` call must still be a constant expression, or the program is ill-formed at that function's definition.
</details>

## Summary

| Form | Condition | Key rules |
|---|---|---|
| `if (c)` | contextually converted to `bool` | entering the first branch via a label evaluates no condition and executes no `else`; `else` binds to the nearest unpaired `if` |
| `if (init; c)` | same as above | as if wrapped in another block; init and c are in the same scope |
| `if constexpr (c)` | a constant expression after conversion to `bool`, narrowing allowed | discarded branches are not instantiated inside templates; checked as usual outside; odr-use requires no definition; `return` takes no part in deduction; no jumping into branches |
| `if consteval { }` | none; depends on whether manifestly constant-evaluated | branches must be compound statements; the first branch is an immediate function context; `if !consteval` is a rewrite |
| `switch (c)` | integral, enumeration or class type, then integral promotion | cases are converted constant expressions of the adjusted type, with no duplicates; at most one `default`; no skipping non-vacuous initialization |
