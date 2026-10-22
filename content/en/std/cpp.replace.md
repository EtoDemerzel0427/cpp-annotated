---
title: Macro replacement
summary: "How object-like and function-like macros are defined and invoked; how arguments are delimited and why they are expanded before substitution; __VA_ARGS__ and __VA_OPT__; the exact rules of # stringizing and ## concatenation; macro redefinition, forbidden names and scope. Rescanning is covered in cpp.rescan."
updated: 2026-10-19
---

!!! tldr
    - Macro replacement works only at the level of preprocessing tokens and knows nothing of scopes, types or expressions; a function-like macro is expanded only when its name is immediately followed by `(`.
    - Arguments are separated by commas, and only parentheses protect commas, so `std::map<int, int>` is split into two arguments; an empty argument counts as an argument.
    - Ordinary parameters are replaced by the fully expanded argument, while operands of `#` and `##` use the argument as written. This is the principle behind the two-level `xstr(x) str(x)` macros.
    - `__VA_OPT__(x)` produces `x` only when the variable arguments are nonempty after expansion, which solves the extra-comma problem.
    - When `#` or `##` produces an invalid result, the program is ill-formed; macro definitions ignore block structure and remain in effect until `#undef` or the end of the translation unit.

Macro replacement happens in translation phase 4 ([[lex.phases]]). It operates on preprocessing tokens ([[g:preprocessing-token]], see [[lex.pptoken]]), not on characters and not on C++ expressions: the preprocessor doesn't know what types, scopes or precedence are; it just replaces one sequence of tokens with another according to rules.

A function-like macro invocation goes through the following steps; this page covers the first four in turn:

1. recognize the invocation and delimit the arguments;
2. argument substitution: ordinary parameters are replaced by fully expanded arguments, operands of `#` and `##` by the arguments as written;
3. perform `#` (stringizing) and `##` (concatenation);
4. remove the placemarkers produced during concatenation;
5. rescan the result together with the rest of the source for more macros, without re-expanding macros currently being expanded; see [[cpp.rescan]].

## Object-like and function-like macros (¶8, ¶11–¶13)

```cpp
#define TABSIZE 100
int table[TABSIZE];              // object-like macro: int table[100];

#define max(a, b) ((a) > (b) ? (a) : (b))
int m = max(1, 2);               // function-like macro: ((1) > (2) ? (1) : (2))
```

¶8 The identifier immediately following `define` is called the **[[g:macro-name|macro name]]**. There is one name space for macro names, with no scopes and no overloading: an object-like macro `X` and a function-like macro `X` can't coexist. Whitespace at the start and end of the replacement list isn't part of the replacement list.

¶11 `#define identifier replacement-list` defines an **[[g:object-like-macro|object-like macro]]**: each subsequent occurrence of the macro name is replaced by the replacement list, which is then rescanned. Example 2 in ¶12 is the `TABSIZE` above.

Footnote 117 points out that by the time of macro replacement, character literals and string literals are already complete preprocessing tokens, so macro names and parameters aren't searched for inside them:

```cpp run title="no-expand-in-literal.cpp" ok
#define N 10
const char* s = "N";      // still "N", not "10"
int main() { return s[0] == 'N' ? 0 : 1; }
```

¶13 When the macro name is immediately followed by `(` (with no whitespace between), it defines a **[[g:function-like-macro|function-like macro]]**, with parameters in the parentheses, which can be a list of identifiers, `...`, or a list of identifiers plus `...`. Afterwards, when the next preprocessing token after the macro name is `(`, an invocation begins, continuing up to the matching `)`, skipping matched pairs of parentheses in between. Newlines within an invocation count as ordinary whitespace, so an invocation can span many lines.

Whether the next token is `(` decides whether a function-like macro is expanded:

```cpp
#define min(a, b) ((a) < (b) ? (a) : (b))
int x = min(1, 2);          // expanded
int y = (std::min)(1, 2);   // not expanded: min is followed by ), not (
auto f = min;               // not expanded: a function-like macro name on its own is an ordinary identifier
```

`(std::min)(a, b)` is the usual way to deal with the `min` and `max` macros in `<windows.h>`, and this is why it works.

Example 3 in ¶15 uses `max` to show the drawbacks of function-like macros: it evaluates one of its arguments twice (along with side effects), generates more code than a function when invoked many times, and a macro has no address. The parentheses ensure the arguments and the result expression associate correctly.

```cpp run title="max-double-eval.cpp" ok
#define max(a, b) ((a) > (b) ? (a) : (b))
int main() {
  int i = 1, j = 0;
  int m = max(i++, j);   // i++ is evaluated twice: once in the comparison, again as the result
  return (m == 2 && i == 3) ? 0 : 1;
}
```

## Delimiting arguments (¶5, ¶14, ¶16)

```cpp
#define TWO(x, y) [x|y]
TWO({1,2})                   // [{1|2}]                  braces don't protect commas
TWO(std::map<int,int>)       // [std::map<int|int>]      angle brackets don't protect commas
TWO((std::map<int,int>), z)  // [(std::map<int,int>)|z]  parentheses protect commas
```

¶14 The tokens between the outermost pair of parentheses form the argument list, with arguments separated by commas, but commas inside nested matching parentheses don't separate arguments. Only parentheses have this effect; the preprocessor doesn't know that `<` starts a template argument list.

When using template types in macros, the common remedies are to add an extra pair of parentheses (if the context allows), to introduce an alias with `using` first, or to make the macro variadic: `#define ONE(...) [__VA_ARGS__]`.

¶5 If the parameter list doesn't end with `...`, the number of arguments must equal the number of parameters, and an empty argument consisting of zero tokens counts as one. If it ends with `...`, the number of arguments must be at least the number of parameters before the `...`. The invocation must have a terminating `)`.

| Macro | Invocation | Number of arguments | Valid? |
|---|---|---|---|
| `#define F0() x` | `F0()` | 0 | yes |
| `#define F1(a) [a]` | `F1()` | 1 (one empty argument) | yes, expands to `[]` |
| `#define F2(a,b) [a b]` | `F2(,)` | 2 (two empty arguments) | yes |
| `#define F2(a,b) [a b]` | `F2()` | 1 | no |
| `#define V(a, ...) a` | `V(1)` | 1 | yes (since C++20) |

C++17 and earlier required a variadic macro to have more arguments than the parameters before `...`, so `V(1)` had to be written `V(1,)`; C++20 relaxed this to at least equal. Clang gives a C++20 extension warning for `V(1)` under `-std=c++17 -pedantic`.

¶16 If the parameter list ends with `...`, the extra arguments, together with the commas between them, are merged into one item called the **[[g:variable-arguments|variable arguments]]**. When `#define V(a, ...)` is invoked as `V(1, 2, 3)`, `a` is `1` and the variable arguments are `2, 3`, comma included.

The second sentence of ¶14 specifies that if the argument list contains a sequence of tokens that would otherwise act as a preprocessing directive, the program is ill-formed. Footnote 118 adds that conditionally-supported directives count too.

```cpp title="directive-in-args.cpp" error
#define M(a) a
int x = M(1
#ifdef BIG
  + 1000
#endif
);
```

In C++23 and earlier this was UB. Clang and GCC both actually execute the `#ifdef` here; Clang gives a `-Wembedded-directive` warning whose wording still says undefined behavior.

## Arguments are expanded first, then substituted ([cpp.subst] paragraph 1)

```cpp run title="two-level.cpp" ok
#define str(x)  #x
#define xstr(x) str(x)
#define N 42
static_assert(__builtin_strlen(str(N)) == 1);    // "N": the operand of # isn't expanded
static_assert(__builtin_strlen(xstr(N)) == 2);   // "42": xstr's x is first expanded to 42,
                                                 // then passed to str
int main() {}
```

Paragraph 1 of [[cpp.subst]]: after the arguments are identified, argument substitution takes place. A parameter in the replacement list that is neither preceded by `#` or `##` nor followed by `##` is replaced by the tokens of the corresponding argument after full macro expansion. Operands of `#` and `##` are handled by their own rules, using the argument as written (see below).

In `str(N)`, `x` is the operand of `#` and gets the unexpanded `N`, giving `"N"`. In `xstr(N)`, `x` isn't the operand of `#`, so it's first expanded to `42` and then substituted, and `str(42)` gives `"42"`. Whenever you want to stringize or concatenate a macro's value, you need an extra layer like this.

An argument is expanded as if it were the rest of the translation unit, with no tokens after it. That is, a function-like macro name at the end of an argument can't borrow a `(` from outside the argument to complete an invocation. Example 1 of paragraph 1:

```cpp
#define LPAREN() (
#define G(Q) 42
#define F(R, X, ...)  __VA_OPT__(G R X) )
int x = F(LPAREN(), 0, <:-);    // replaced by int x = 42;
```

The argument `R` is `LPAREN()`, fully expanded to `(`; `X` is `0`; the variable arguments are `<:-`, nonempty. Substituting into `__VA_OPT__(G R X)` gives `G ( 0`, and only when rescanned together with the `)` at the end of the replacement list does it form the invocation `G(0)`, giving `42`. `G` and `(` meet during rescanning, not during argument expansion.

## Variable arguments: __VA_ARGS__ and __VA_OPT__ (¶6, [cpp.subst] paragraphs 2–4)

Paragraph 2 of [[cpp.subst]]: `__VA_ARGS__` in the replacement list is treated as a parameter and replaced by the variable arguments. Example 2 in paragraph 3:

```cpp
#define debug(...) fprintf(stderr, __VA_ARGS__)
#define showlist(...) puts(#__VA_ARGS__)
#define report(test, ...) ((test) ? puts(#test) : printf(__VA_ARGS__))
debug("Flag");                              // fprintf(stderr, "Flag");
debug("X = %d\n", x);                       // fprintf(stderr, "X = %d\n", x);
showlist(The first, second, and third items.);
                                            // puts("The first, second, and third items.");
report(x>y, "x is %d but y is %d", x, y);   // ((x>y) ? puts("x>y") : printf("x is %d but y is %d", x, y));
```

`showlist` shows that `#__VA_ARGS__` stringizes the commas in the variable arguments too.

¶6 `__VA_ARGS__` and `__VA_OPT__` may appear only in the replacement list of a function-like macro that uses `...`. Clang warns about `__VA_ARGS__` appearing elsewhere only under `-pedantic`.

### __VA_OPT__ solves the extra comma

Before C++20, variadic macros had an old problem:

```cpp
#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
LOG("hi");          // printf("hi", ): an extra comma, a syntax error
```

GCC's extension `, ## __VA_ARGS__`, which swallows the preceding comma when the variable arguments are empty, was popular for many years, but it isn't standard and its semantics are odd. C++20's `__VA_OPT__` ([[P0306R4]], with wording revised by [[P1042R1]]) provides the standard way:

```cpp
#define LOG(fmt, ...) printf(fmt __VA_OPT__(,) __VA_ARGS__)
LOG("hi");          // printf("hi" )
LOG("%d", 1);       // printf("%d" , 1)
```

The rules of paragraph 4 of [[cpp.subst]]:

1. `__VA_OPT__` may appear only in the form `__VA_OPT__( tokens )`, and the parentheses can't contain another `__VA_OPT__`.
2. If the tokens in the parentheses would be ill-formed as the replacement list of this macro (for example, beginning with `##`), the program is ill-formed.
3. `__VA_OPT__(...)` as a whole is treated as a parameter. If `__VA_ARGS__` would be replaced by no tokens at all, the corresponding argument is a placemarker (see the `##` section), that is, it produces nothing; otherwise, the corresponding argument is the result of expanding the tokens in the parentheses as a replacement list (performing argument substitution, `#` and `##`), before placemarkers are removed and before rescanning.

What's checked is whether `__VA_ARGS__` is empty after replacement, and when `__VA_ARGS__` is replaced the variable arguments have already been fully expanded. So a macro that expands to nothing counts as empty too:

```cpp
#define F(...)           f(0 __VA_OPT__(,) __VA_ARGS__)
#define G(X, ...)        f(0, X __VA_OPT__(,) __VA_ARGS__)
#define SDEF(sname, ...) S sname __VA_OPT__(= { __VA_ARGS__ })
#define EMP

F(a, b, c)          // f(0, a, b, c)
F()                 // f(0)
F(EMP)              // f(0): EMP expands to nothing
G(a, b, c)          // f(0, a, b, c)
G(a, )              // f(0, a): the variable arguments are one empty argument
G(a)                // f(0, a): no variable arguments (valid since C++20)
SDEF(foo);          // S foo;
SDEF(bar, 1, 2);    // S bar = { 1, 2 };
```

This is the first half of Example 3 in paragraph 4. `SDEF` shows that `__VA_OPT__` isn't only for commas; any tokens needed only when there are variable arguments can go in it. The second half of Example 3 concerns how `__VA_OPT__` interacts with `#` and `##`, and comes after those two operators are covered.

## The # operator: stringizing ([cpp.stringize])

```cpp
#define str(x) #x
str(  a   +    b  )        // "a + b": whitespace normalized
str(a "\n" b)              // "a \"\\n\" b": " and \ inside the literal are escaped
str('"')                   // "'\"'"
str()                      // ""
str(R"(line1
line2)")                   // "R\"(line1\nline2)\"": a real newline becomes \n
```

Paragraph 1 of [[cpp.stringize]]: each `#` in the replacement list of a function-like macro must be followed by a parameter. A `#` in an object-like macro is just an ordinary token and isn't subject to this.

```cpp
#define S(a) #b     // error: # isn't followed by a parameter
#define HASH #      // OK: object-like macro; # is just an ordinary token
```

Paragraph 2: when a parameter immediately follows `#`, both are replaced by a single string literal with no prefix (which the standard calls a [[g:character-string-literal|character string literal]]) containing the spelling of the corresponding argument (with placemarkers removed). Specifically:

- each occurrence of whitespace between the argument's tokens becomes a single space, and leading and trailing whitespace is deleted;
- each token keeps its original spelling, except that inside header names, character literals and string literals (including the delimiting `"`), a `\` is inserted before each `"` and `\`, and each newline character is replaced by the two characters `\n`;
- an empty argument gives `""`;
- if the result isn't a valid string literal, the program is ill-formed;
- the order of evaluation of `#` and `##` is unspecified.

The rule replacing newlines with `\n` is for raw string literals: raw string literals can contain real newlines, ordinary string literals can't, so they have to be rewritten.

!!! lawyer "Escaping happens only inside literals"
    A `\` outside a literal is a separate preprocessing token and isn't escaped. So `str(\)` gives `"\"`, which isn't a valid string literal, and the program is ill-formed. Clang 23 gives only an invalid string literal, ignoring final '\' warning, with the result `""`.

!!! lawyer "The amount of whitespace doesn't affect the result"
    Whether consecutive non-newline whitespace is kept or compressed to one space in phase 3 is unspecified ([[lex.phases]]). But this doesn't affect stringizing, because each occurrence of whitespace becomes one space; only whether there is whitespace affects the result, and that's decided in phase 3. So `str(a+b)` is always `"a+b"` and `str(a + b)` always `"a + b"`.

## The ## operator: token concatenation ([cpp.concat])

```cpp
#define CAT(a, b) a ## b
CAT(x, 1)        // x1
CAT(+, =)        // +=
CAT(/, /)        // error: // isn't a preprocessing token; comments were handled in phase 3
CAT(+, -)        // error: +- isn't a single preprocessing token
CAT(., .)        // error: .. isn't a preprocessing token (... is)
```

Paragraph 1 of [[cpp.concat]]: `##` can't appear at the beginning or end of a replacement list; it needs two operands.

Paragraph 2: in a function-like macro, a parameter immediately adjacent to `##` (before or after) is replaced by the corresponding argument's tokens as written, without expansion. If the argument is empty, it's replaced by a **[[g:placemarker|placemarker]]**. Footnote 119 explains that placemarkers don't appear in the grammar; they're just temporary entities internal to phase 4.

Paragraph 3: before rescanning, each `##` in the replacement list that didn't come from an argument is deleted, and the tokens before and after it are concatenated into one token. A placemarker concatenated with a placemarker gives a placemarker, and a placemarker concatenated with another token gives that token. If the result of concatenation isn't a valid preprocessing token, the program is ill-formed; in C++23 and earlier this was UB. The resulting token is available for further macro replacement. Note 1 points out that concatenation can form a universal character name. Clang reports pasting formed '...', an invalid preprocessing token for all three errors above.

The qualification "didn't come from an argument" means a `##` written in an argument is just an ordinary token:

```cpp
#define F(x) [x]
F(a ## b)        // [a ## b]: the ## came from the argument, not an operator in F's replacement list
```

!!! lawyer "Unspecified concatenation order, and when it matters"
    The order of concatenation in `a ## b ## c` is unspecified. Usually the result is the same, but not when an intermediate result isn't a valid token:
    ```cpp
    #define cat3(a, b, c) a ## b ## c
    cat3(-, >, *)   // left to right: -> then ->*, valid; right to left: >* isn't a token, ill-formed
    ```
    Clang 23 processes left to right, giving `->*`. Portable code should ensure intermediate results are valid in any order.

### A complete two-level example

Example 1 in paragraph 4 of [[cpp.concat]] combines `#`, `##` and argument expansion:

```cpp
#define str(s)      # s
#define xstr(s)     str(s)
#define debug(s, t) printf("x" # s "= %d, x" # t "= %s", \
               x ## s, x ## t)
#define INCFILE(n)  vers ## n
#define glue(a, b)  a ## b
#define xglue(a, b) glue(a, b)
#define HIGHLOW     "hello"
#define LOW         LOW ", world"

debug(1, 2);
fputs(str(strncmp("abc\0d", "abc", '\4')        // this goes away
    == 0) str(: @\n), s);
#include xstr(INCFILE(2).h)
glue(HIGH, LOW);
xglue(HIGH, LOW)
```

The result is:

```cpp
printf("x" "1" "= %d, x" "2" "= %s", x1, x2);
fputs("strncmp(\"abc\\0d\", \"abc\", '\\4') == 0" ": @\n", s);
#include "vers2.h"      // after macro replacement, before file access
"hello";
"hello" ", world"
```

Line by line:

- `debug(1, 2)`: `# s` gives `"1"` and `x ## s` gives `x1`. Phase 6 then concatenates the adjacent string literals into `"x1= %d, x2= %s"`.
- `fputs(...)`: the argument spans lines, and the line comment had already become a space in phase 3, so "this goes away". When stringizing, the `"` and `\` in `"abc\0d"` are escaped. In `str(: @\n)`, the `@`, `\` and `n` aren't inside a literal and are kept as is, giving `": @\n"`, which in phase 7 happens to be a valid string with a newline escape.
- `#include xstr(INCFILE(2).h)`: `xstr`'s argument is first fully expanded, `INCFILE(2)` becoming `vers2`, giving `vers2.h`, which `str` stringizes into `"vers2.h"`. This is the typical use of the macro form of [[cpp.include]].
- `glue(HIGH, LOW)`: `a` and `b` are adjacent to `##`, so they aren't expanded and are concatenated directly into `HIGHLOW`; on rescanning, `HIGHLOW` is a macro, giving `"hello"`.
- `xglue(HIGH, LOW)`: `xglue`'s parameters aren't adjacent to `##`, so the arguments are expanded first. `HIGH` isn't a macro; `LOW` expands to `LOW ", world"`, where the inner `LOW` isn't expanded again within its own expansion ([[cpp.rescan]]). So `glue(HIGH, LOW ", world")` gives `HIGHLOW ", world"`, which then gives `"hello" ", world"`.

The end of the example notes that whitespace around `#` and `##` in macro definitions is optional: `# s` and `#s`, `a ## b` and `a##b` are equivalent.

### A ## formed by concatenation isn't an operator

Example 2 in paragraph 5:

```cpp
#define hash_hash # ## #
#define mkstr(a) # a
#define in_between(a) mkstr(a)
#define join(c, d) in_between(c hash_hash d)
char p[] = join(x, y);          // equivalent to char p[] = "x ## y";
```

The expansion proceeds `join(x, y)`, `in_between(x hash_hash y)`, `in_between(x ## y)`, `mkstr(x ## y)`, and finally `"x ## y"`. In `hash_hash`'s replacement list `# ## #`, the middle `##` is an operator that concatenates the two `#` into a `##` token. But this new token isn't the `##` operator, because paragraph 3 only processes `##` originally in the replacement list. It's passed down as part of an argument and finally stringized as is.

### Placemarkers

Example 3 in paragraph 6:

```cpp
#define t(x,y,z) x ## y ## z
int j[] = { t(1,2,3), t(,4,5), t(6,,7), t(8,9,),
  t(10,,), t(,11,), t(,,12), t(,,) };
// result: int j[] = { 123, 45, 67, 89, 10, 11, 12, };
```

In `t(6,,7)`, the empty argument `y` becomes a placemarker, and `6 ## placemarker ## 7` gives `67`. The three empty arguments of `t(,,)` all become placemarkers, which concatenate to a placemarker that is finally removed, leaving nothing, so the initializer ends with `12, `, leaving a valid trailing comma. Placemarkers give every `##` two operands, so there's no need to separately discuss what concatenating with nothing means.

### __VA_OPT__ with # and ##

Back to the second half of Example 3 in paragraph 4 of [[cpp.subst]]:

```cpp
#define H1(X, ...) X __VA_OPT__(##) __VA_ARGS__   // error: ## can't appear at the beginning of a replacement list
#define H2(X, Y, ...) __VA_OPT__(X ## Y,) __VA_ARGS__
H2(a, b, c, d)      // ab, c, d
#define H3(X, ...) #__VA_OPT__(X##X X##X)
H3(, 0)             // ""
#define H4(X, ...) __VA_OPT__(a X ## X) ## b
H4(, 1)             // a b
#define H5A(...) __VA_OPT__()/**/__VA_OPT__()
#define H5B(X) a ## X ## b
#define H5C(X) H5B(X)
H5C(H5A())          // ab
```

- `H1`: the `##` in the parentheses of `__VA_OPT__`, treated as a replacement list, is at the beginning, violating paragraph 1 of [[cpp.concat]]; ill-formed.
- `H2`: `##` works as usual inside `__VA_OPT__`, forming `ab`.
- `H3`: `#` can apply to `__VA_OPT__`, because it's treated as a parameter. The variable argument `0` is nonempty, so the parenthesized contents are expanded: `X` is an empty argument adjacent to `##` and becomes a placemarker, and both concatenations give placemarkers. Placemarkers are removed before stringizing, and stringizing an empty sequence gives `""`.
- `H4`: `__VA_OPT__(...)` as a whole is the left operand of `##`. Its corresponding argument is the result of expanding `a X ## X`, namely `a placemarker`, with the placemarker not yet removed. Then `placemarker ## b` gives `b`, and the result is `a b`, not `ab`, because what's concatenated with `b` is the placemarker, not `a`.
- `H5`: `H5A()` has empty variable arguments, so both `__VA_OPT__` produce only placemarkers, which are finally removed; `H5A()` expands to nothing. So `H5B` receives an empty argument, and `a ## placemarker ## b` gives `ab`.

!!! impl "Tested"
    For `F`, `G`, `SDEF`, `H2` through `H5` and `LPAREN` on this page, and the three standard examples of [[cpp.concat]], Clang 23's `-E` output agrees with the standard (apart from whitespace).

## Restrictions on defining macros (¶1–¶4, ¶7, ¶9, ¶10)

### Redefinitions must be identical (¶1–¶3)

<div class="compare" markdown="1">

```cpp run ok
#define OBJ_LIKE (1-1)
#define OBJ_LIKE /* whitespace */ (1-1) /* other */
#define FUNC_LIKE(a)   ( a )
#define FUNC_LIKE( a )(  \
            a /* spans
              lines */ )
int main() {}
```

```cpp error
#define OBJ_LIKE (1-1)
#define OBJ_LIKE (0)       // different tokens
#define OBJ_LIKE (1 - 1)   // different whitespace
#define FUNC_LIKE(a) ( a )
#define FUNC_LIKE(b) ( a ) // different use of the parameter
#define FUNC_LIKE(b) ( b ) // different parameter spelling
```

</div>

This is Example 1 in ¶3. ¶1 Two replacement lists are **identical** if and only if their preprocessing tokens have the same number, ordering, spelling and whitespace separation, where all whitespace separations are considered identical. That is, whether there is whitespace between two tokens must match, but how much and what kind doesn't matter. Comments have become spaces by phase 3, so the forms on the left are all identical.

¶2 An identifier already defined as an object-like macro can be redefined only by an object-like macro with an identical replacement list; a function-like macro additionally requires the same number and spelling of parameters. Otherwise the program is ill-formed.

Requiring token-by-token identity rather than semantic equivalence is because the same macro is often defined repeatedly in several headers; C's `NULL`, for example, is defined in several standard headers. Token-by-token comparison allows such harmless repetition while simply catching real conflicts.

!!! note "Clang only warns"
    For incompatible redefinitions, Clang gives only a `-Wmacro-redefined` warning and then uses the new definition. A warning is a diagnostic in the standard's sense, so this conforms. But many projects have come to rely, without realizing it, on later definitions overriding earlier ones; the portable approach is to `#undef` first.

### Other formal requirements (¶4, ¶7, ¶10)

¶4 There must be whitespace between the macro name and the replacement list of an object-like macro. `#define NOSPACE+1` violates this; Clang gives an ISO C99 requires whitespace after the macro name warning.

¶7 The parameters of a function-like macro can't have duplicate names; `#define G(x, x) x` is ill-formed, and Clang reports duplicate macro parameter name.

¶10 Where a preprocessing directive could begin, an identifier after `#` isn't subject to macro replacement. So after `#define include xxx`, `#include` is still `#include`.

### Names that can't be defined as macros (¶9)

¶9 A translation unit shall not `#define` or `#undef` macro names spelled the same as:

- keywords ([[lex.key]]);
- the identifiers with special meaning in Table 4: `final`, `import`, `module`, `override`, `post`, `pre` ([[lex.name]]);
- attribute names described in [[dcl.attr]], such as `noreturn`, `nodiscard`, `deprecated`, `fallthrough`, `assume`.

The exceptions are `likely` and `unlikely`, which may be defined as function-like macros and may be `#undef`ed.

```cpp title="reserved-macro-names.cpp" error
#define new  my_new      // error: keyword
#define override         // error: Table 4
#define pre  1           // error: Table 4 (pre in C++26 contracts)
#define noreturn         // error: attribute name
#define likely(x) __builtin_expect(!!(x), 1)   // OK: likely may be a function-like macro
#define unlikely 0       // error: unlikely may only be defined as a function-like macro
```

The exception is a compromise with reality: lots of C code, such as the Linux kernel, has long defined `likely(x)` and `unlikely(x)` macros. A function-like macro expands only when immediately followed by `(`, while in `[[likely]]`, `likely` is followed by `]`, so the two don't interfere; an object-like `#define likely` would break `[[likely]]`.

Note 1 points out that alternative tokens such as `and` and `bitor` ([[lex.digraph]]) aren't identifiers, so a macro named `and` can't be defined at all.

!!! impl "Implementation status"
    Clang 23 gives a `-Wkeyword-macro` warning for `#define new ...` and `#define override`, and no diagnostic for `#define noreturn`, `#define pre 1` or `#define unlikely 0`. So on Clang only part of this rule is checked.

Two other places have similar restrictions: a translation unit that includes a standard library header shall not `#define` or `#undef` any name declared in any standard library header, for example `#define move ...` isn't allowed ([[macro.names]]); predefined macro names and `defined` shall not be `#define`d or `#undef`ed either ([[cpp.predefined#4]]).

## Scope of macros ([cpp.scope])

```cpp run title="macro-scope.cpp" ok
void f() {
#define LOCAL 1          // not actually local
}
namespace n {
  int g() { return LOCAL; }   // still visible: macros ignore scopes and namespaces
}
#undef LOCAL
#undef NEVER_DEFINED     // OK: ignored
int main() { return n::g() - 1; }
```

Paragraph 1 of [[cpp.scope]]: a macro definition lasts from where it's defined, independent of block structure, until a corresponding `#undef`, or if there's none, until the end of the translation unit. Macro definitions have no significance after phase 4.

Paragraph 2: `#undef identifier` causes the identifier to no longer be a macro name. If it wasn't a macro name, the directive is ignored; it isn't an error.

Macros ceasing to exist after phase 4 means debuggers can't see macros (unless the compiler records them separately, as GCC's and Clang's `-g3` do), named modules don't export macros ([[cpp.import]]), and macros don't take part in linking. Two translation units can give the same macro name completely different definitions. But if a macro affects the tokens of some `inline` function or class definition after expansion, and the definition's tokens differ between two translation units, that violates the ODR ([[basic.def.odr]]): the program is ill-formed, no diagnostic required.

!!! tip "push_macro and pop_macro"
    The standard provides no mechanism for temporarily changing a macro and restoring the original definition afterwards. GCC, Clang and MSVC all support `#pragma push_macro("X")` and `#pragma pop_macro("X")`, which are implementation-defined pragmas ([[cpp.pragma]]).

## Common pitfalls

!!! pitfall "Multi-statement macros"
    ```cpp
    #define SWAP(a, b) tmp = a; a = b; b = tmp
    if (x > y) SWAP(x, y);    // only the first statement is controlled by the if
    ```
    The idiomatic form is `#define SWAP(a, b) do { auto t = a; a = b; b = t; } while (0)`. It's a single statement, and it requires a semicolon at the call site, so it's used just like a function call.

!!! pitfall "No parentheses around parameters"
    ```cpp
    #define SQ(x) x * x
    SQ(1 + 2)     // 1 + 2 * 1 + 2, which is 5
    ```
    Macros replace only tokens and ignore precedence. Every parameter in the replacement list, and the whole replacement list, should be parenthesized.

!!! pitfall "Template commas in arguments"
    `ASSERT(std::is_same_v<A, B>)` is split into two arguments. Add a pair of parentheses: `ASSERT((std::is_same_v<A, B>))`.

## History

!!! history
    - C++98 macros were the same as C89's: object-like macros, function-like macros, `#` and `##`. Empty arguments were UB then.
    - C++11 caught up with C99 ([[N1653]]), adding variadic macros and `__VA_ARGS__`, allowing empty arguments, and introducing the placemarker rules.
    - C++20 added `__VA_OPT__` ([[P0306R4]], with wording revised by [[P1042R1]]) and allowed variadic macros to omit all variable arguments.
    - Wording after C++23 turned several kinds of UB into ill-formed: `##` forming an invalid token, directives in arguments, stringizing results that aren't valid string literals, and so on.

## Questions

!!! question "Question 1"
    What does each invocation below expand to?
    ```cpp
    #define F(x, ...) f(x __VA_OPT__(,) __VA_ARGS__)
    #define E
    F(1)
    F(1,)
    F(1, E)
    F(1, E E, )
    F(, 2)
    ```

<details markdown="1">
<summary>Answer</summary>

- `F(1)` gives `f(1 )`: no variable arguments, valid since C++20.
- `F(1,)` gives `f(1 )`: the variable arguments are one empty argument.
- `F(1, E)` gives `f(1 )`: `__VA_ARGS__` is empty after replacement, and paragraph 4 of [[cpp.subst]] looks at the result of replacement.
- `F(1, E E, )` gives `f(1 , ,)`: the variable arguments are `E E,`, which expand to a comma, not empty, so `__VA_OPT__(,)` produces a comma. Commas in the variable arguments belong to the variable arguments (¶16).
- `F(, 2)` gives `f( , 2)`: `x` is an empty argument and the variable argument is `2`.

All these results were verified with Clang 23's `-E`.
</details>

!!! question "Question 2"
    Why does `glue(HIGH, LOW)` give `"hello"` while `xglue(HIGH, LOW)` gives `"hello" ", world"`? What happens to `xglue(HIGH, LOW)` if `LOW` is changed to `#define LOW "!"`?

<details markdown="1">
<summary>Answer</summary>

`glue`'s parameters are adjacent to `##`, so the arguments aren't expanded and are concatenated directly into `HIGHLOW`. `xglue`'s parameters aren't adjacent to `##`, so the arguments are fully expanded first: `LOW` becomes `LOW ", world"`, where the inner `LOW` isn't expanded again. Then `glue` concatenates `HIGH` with this no-longer-expanded `LOW`, giving `HIGHLOW`. That's a new token, which expands to `"hello"` on rescanning, followed by `", world"`.

With `#define LOW "!"`, `xglue` first expands `LOW` to `"!"`, and `glue(HIGH, "!")` has to concatenate `HIGH` and `"!"` into one token; the resulting `HIGH"!"` isn't a valid preprocessing token (`HIGH` isn't a string literal prefix), so the program is ill-formed. Clang 23 reports pasting formed 'HIGH"!"', an invalid preprocessing token.
</details>

!!! question "Question 3"
    After `#define EMPTY`, is `F(EMPTY)` for `#define F(x) #x` `""` or `"EMPTY"`? What about `G(EMPTY)` for `#define G(x) F(x)`?

<details markdown="1">
<summary>Answer</summary>

`F(EMPTY)` is `"EMPTY"`: the operand of `#` uses the argument as written, unexpanded. `G(EMPTY)` is `""`: `G`'s `x` isn't the operand of `#`, so the argument is first fully expanded to nothing, `F` receives an empty argument, and stringizing gives `""`.
</details>

## Summary

!!! summary
    - Redefinitions must be identical token by token, with whitespace mattering only by presence; function-like macros also require the same number and spelling of parameters.
    - Empty arguments count as arguments; `F()` passes one empty argument to a single-parameter macro; only parentheses protect commas in arguments.
    - Keywords, `final`, `override`, `import`, `module`, `pre`, `post` and standard attribute names can't be defined as macros; `likely` and `unlikely` can be defined only as function-like macros.
    - Arguments are fully expanded before substitution unless they're operands of `#` or `##`, which is the principle behind the two-level macro idiom.
    - `__VA_OPT__(x)` produces `x` only when `__VA_ARGS__` is nonempty after replacement.
    - `#` normalizes whitespace to single spaces and escapes `"` and `\` in literals; `##` is ill-formed if it can't form a valid token, empty arguments become placemarkers, and a `##` formed by concatenation isn't an operator.
    - Macro definitions ignore block structure, last until `#undef` or the end of the translation unit, and cease to exist after phase 4.
