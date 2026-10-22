---
title: Ambiguity resolution
summary: "How to choose when a function-style cast and a declaration look the same: whatever can be a declaration is a declaration, whatever can be a type-id is a type-id. Covers the most vexing parse, ambiguities in template arguments and sizeof, and parenthesized type names in parameters."
updated: 2026-10-19
---

!!! tldr
    - `T(x)` can be an expression converting `x` to `T`, or a declaration of the variable `x` (with an extra pair of parentheses around the name). The standard's rule: whatever can be read as a declaration is a declaration.
    - So `S v(int(a));` and `Widget w();` both declare functions. Using braces, adding another pair of parentheses, or writing `=` gives you an object.
    - Where both a type and an expression may be written (template arguments, `typeid`), whatever can be read as a type-id is a type-id, so `Y<int()>` is an error for a non-type template parameter.
    - In the current draft, `sizeof`, `alignof` and C-style casts only accept a *nofun-type-id*, which can't denote a function type, so `sizeof(int())` has become an expression. Clang 23 still reports errors under the old rule.
    - A parenthesized type name in a parameter list is treated as a type: the parameter of `void f(int(C));` is a function pointer, not an `int` named `C`.

## Where the ambiguity comes from

C++ has function-style type conversions `T(x)` ([[expr.type.conv]]) and also inherited C's declarator grammar, in which declarators can be parenthesized at will ([[dcl.decl]]): `int (a)` is just `int a`. So the same token sequence often has two readings:

| Tokens | Expression reading | Declaration reading |
|---|---|---|
| `int(a)` | Convert `a` to `int` | An `int` named `a`, with redundant parentheses around the name |
| `int()` | A value-initialized `int`, value 0 | The type of a function with no parameters returning `int` |

The grammar itself can't tell them apart, so the standard can only give preference rules. The ambiguity of whether a whole statement is an expression statement or a declaration statement is handled in [[stmt.ambig]]; this subclause handles three ambiguities that occur inside declarations, and the idea behind the rules is the same each time.

## Object or function (¶1)

```cpp run ok
#include <type_traits>
struct S { S(int); };
typedef struct BB { int C[2]; } *B, C;

void foo(double a) {
  S v(int(a));      // function declaration: S v(int a)
  S w(int());       // function declaration: the parameter is a function returning int, adjusted to int(*)()
  S x((int(a)));    // object declaration
  S y((int)a);      // object declaration
  S z = int(a);     // object declaration
  S b(auto()->C);   // function declaration: the parameter is a function returning C, adjusted to C(*)()

  static_assert(std::is_same_v<decltype(v), S(int)>);
  static_assert(std::is_same_v<decltype(w), S(int (*)())>);
  static_assert(std::is_same_v<decltype(b), S(C (*)())>);
}
int main() { }
```

¶1 `S v(int(a));` can be an object `v` initialized with `int(a)`, or a function `v` whose parameter is written `int(a)`, i.e. `int a` with redundant parentheses. As in [[stmt.ambig]], the standard says any construct that could possibly be a declaration is treated as a declaration, so `v` is a function.

`S w(int())` is also a function. As an abstract declarator, `int()` denotes the type of a function returning `int`; used as a parameter type it is adjusted to the function pointer `int(*)()` per [[dcl.fct#5]].

`x`, `y` and `z` are objects, because `(int(a))` with an extra outer pair of parentheses and the C-style cast `(int)a` can't possibly be parameter declarations, and copy-initialization `= int(a)` isn't read as a declaration either.

### The trailing-return-type form must start with auto

The last sentence of ¶1 handles a special form: if a construct can syntactically be a declaration and its outermost declarator would match the grammar of a declarator with a trailing return type, it is a declaration only if it starts with `auto`.

```cpp run error
struct S { S(int); };
typedef struct BB { int C[2]; } *B, C;
void foo() {
  S a(B()->C);   // object declaration: B() doesn't start with auto
}                // error: but S can't be initialized with int[2]
```

Grammatically, `B()->C` could be read as the parameter type `B() -> C`, i.e. a function returning `C`. But a trailing return type requires the specifier to be `auto` alone ([[dcl.fct#1]]), so that reading is doomed to be ill-formed. Without this sentence, the "read it as a declaration if you can" rule would choose it and turn a possibly valid expression into an error. With it, `B()->C` is read as an expression: `B()` is a value-initialized null pointer and `->C` accesses the member array. This example still ends in an error, but the error is semantic (`S` has no constructor taking `int*`), not a parsing one. `S b(auto()->C)` starts with `auto`, so it is still a function declaration.

### The most vexing parse

The most famous consequence of this rule is called the [[g:most-vexing-parse|most vexing parse]]: you meant to construct an object and declared a function instead.

```cpp run error
#include <iterator>
#include <sstream>
#include <vector>

struct Timer { };
struct TimeKeeper { TimeKeeper(Timer); int get(); };

int f() {
  TimeKeeper tk(Timer());   // function declaration: parameter type is Timer(*)()
  return tk.get();          // error: tk is a function
}

void g(std::istringstream& in) {
  std::vector<int> v(std::istream_iterator<int>(in),
                     std::istream_iterator<int>());
  v.size();                 // error: v is a function
}
```

The first parameter `std::istream_iterator<int>(in)` is read as a parameter named `in`, and the second as a function pointer parameter. Clang gives a `-Wvexing-parse` warning for both (parentheses were disambiguated as a function declaration); GCC has a warning of the same name.

Note 1 gives the ways to disambiguate, which boil down to writing a form that can't possibly be a declaration:

| Form | Result |
|---|---|
| `S x{int(a)};` | Object: list-initialization, the preferred choice since C++11 |
| `S x((int(a)));` | Object: an extra pair of parentheses can't be a parameter |
| `S x = int(a);` | Object: copy-initialization |
| `S x((int)a);`, `S x(static_cast<int>(a));` | Object: not a function-style cast |
| `S x(int(a));` | Function |
| `S x();` | Function (the note in [[dcl.init#15]] points this out specifically too) |

The two examples above can be rewritten as `TimeKeeper tk{Timer{}};` and `std::vector<int> v{std::istream_iterator<int>(in), {}};`.

!!! pitfall "A lock that doesn't lock"
    The same kind of problem exists at the statement level ([[stmt.ambig]]):
    ```cpp
    std::lock_guard<std::mutex>(m);   // declares a lock_guard variable named m
    ```
    This statement can be read as a declaration, so it declares a default-constructed local variable `m` that hides the outer mutex. `lock_guard` has no default constructor, so here it happens to be an error; if the guard type were default-constructible, the program would compile quietly without locking anything. Write `std::lock_guard g(m);` or `std::scoped_lock g{m};`.

## type-id or expression (¶2)

### Template arguments and typeid

¶2 The second ambiguity arises where both a *type-id* (a type name, see [[dcl.name]]) and an expression may be written, such as template arguments and `typeid(…)`. The rule: whatever could be a type-id in that syntactic position is a type-id.

"Could" here means syntactically could. `int(1)` can't be a type-id, because `1` can't appear in a declarator, so it must be an expression. `int()` can be a type-id (a function type), so it is a type-id, even though a function type makes no sense here:

```cpp run error
template <class T> struct X {};
template <int N> struct Y {};

X<int()> a;    // type-id: T = int(), OK
X<int(1)> b;   // expression: error, X needs a type
Y<int()> c;    // type-id: error, Y needs a value
Y<int(1)> d;   // expression: N = 1, OK
```

`Y<int()>` shows the cost of this rule: the author obviously wanted `Y<0>`, but parsing doesn't look at what kind of template parameter it is. Clang's diagnostic is template argument for non-type template parameter is treated as function type 'int ()'.

### sizeof, alignof and C-style casts

Note 2 points out that no such ambiguity arises between an expression and a [[g:nofun-type-id|nofun-type-id]]. A nofun-type-id is a type-id whose outermost part can't be a function declarator; this is new wording after C++23. In the current draft, the type operands of `sizeof`, `alignof`, C-style casts `(T)e` and `new (T)` are all nofun-type-ids. The outermost part of `int()` and `int(unsigned(a))` is a function declarator, so they are not nofun-type-ids and can only be read as expressions.

```cpp
void foo(signed char a) {
  sizeof(int());              // expression: sizeof(int{})
  sizeof(int(a));             // expression
  sizeof(int(unsigned(a)));   // expression
  (int())+1;                  // expression: value 1
  (int(a))+1;                 // expression
  (int(unsigned(a)))+1;       // expression
}
```

In C++23, lines 1, 3, 4 and 6 can be read as type-ids, so they were treated as the function types `int()` or `int(unsigned)` and were all ill-formed. `int(unsigned(a))` is especially counterintuitive: `unsigned(a)` looks like a conversion but can be read as the parameter declaration `unsigned a`.

Clang 23 still follows the old rule and reports invalid application of 'sizeof' to a function type and C-style cast from 'int' to 'int ()' is not allowed for these four lines, so this code block carries no verdict. Portable code should write `sizeof(int{})` or `sizeof(int)`.

`alignof` only accepts `alignof( nofun-type-id )` and has no expression form, so under the current draft `alignof(int())` is a syntax error. `typeid` and template arguments still use type-id, and the rule from the previous subsection applies as before.

### The auto requirement here too

¶2 also has a sentence symmetric to the one in paragraph 1: if a construct can syntactically be a type-id and its outermost abstract declarator would match the form with a trailing return type, it is a type-id only if it starts with `auto`.

```cpp run error
typedef struct BB { int C[2]; } *B, C;
void g() {
  (void)sizeof(B()->C[1]);      // OK: sizeof(expression)
  (void)sizeof(auto()->C[1]);   // error
}
```

The first line doesn't start with `auto` and is an expression; the operand of `sizeof` is unevaluated, so the null pointer isn't dereferenced. For the second line, under the current draft the outermost part of `auto() -> C[1]` is a function, so it isn't a nofun-type-id and can only be read as an expression, but `auto()` is not a valid expression, so it is ill-formed. Clang treats it as a type-id under the old rule and reports that a function can't return an array; the conclusion is the same: ill-formed.

## Parenthesized type names in parameters (¶3)

```cpp run error
class C { };
void f(int(C)) { }   // i.e. void f(int (*fp)(C)), not void f(int C)

int g(C);

void foo() {
  f(1);              // error: 1 can't be converted to a function pointer
  f(g);              // OK
}
```

¶3 In a parameter-declaration-clause, `int(C)` can be an `int` parameter named `C` (redundant parentheses) or a parameter of function type taking `C` and returning `int`, adjusted to a function pointer. The rule: the type name in the parentheses is taken as a type specifier, not as a parameter name, so the latter reading wins.

```cpp run ok
#include <type_traits>
class C { };
void h(int *(C[10]));   // parameter: a function taking C[10] (adjusted to C*) and returning int*
static_assert(std::is_same_v<decltype(h), void(int *(*)(C *))>);
int main() { }
```

The reason for this choice is that redeclaring a type name as a parameter name would hide the type, which is almost never what the author intended. The rule only applies when `C` is a type name; if `C` is not a type name, `int(C)` can only be an `int` parameter named `C`.

## The decision is purely syntactic

All three rules are purely syntactic: if a construct can syntactically be read as a declaration (or a type-id), that reading is taken, and even if the resulting declaration is semantically ill-formed, the parser doesn't fall back to an expression ([[stmt.ambig#3]]).

If disambiguation depended on semantics, e.g. switching to an expression when parsing as a declaration fails, parsing would be entangled with overload resolution and template instantiation, and the result could depend on declarations far away. Purely syntactic rules are sometimes counterintuitive, but they are deterministic and local: you only need to know which names are type names.

!!! impl
    To implement these rules, GCC and Clang both use tentative parsing: on meeting a construct that could be a declaration, they first try to parse it as a declaration, adopt that if it parses completely, and otherwise backtrack and parse it as an expression. This needs arbitrarily long lookahead, because a statement like `T(*g)(double(3))` can only be decided at its end.

## History

!!! history
    - The three rules (object or function, type-id or expression, parenthesized type names) have existed since C++98.
    - C++11 list-initialization provided the most direct way around them, because the contents of braces can't be a parameter list.
    - Trailing return types brought new ambiguities like `B()->C`, and later revisions added the restriction that only a form starting with `auto` counts as a declaration or type-id.
    - The draft after C++23 introduced *nofun-type-id*, so `sizeof(int())` and `(int())+1` are no longer ambiguous.

## Questions

!!! question "Question 1"
    What does each line below declare?
    ```cpp
    struct T { T(int); T(); };
    int n = 0;
    void f() {
      T a(T());
      T b(T(n));
      T c(T(1));
      T d((T(n)));
      T e(T(n), T());
    }
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: a function with a parameter of type `T(*)()`, returning `T`.
- `b`: a function whose parameter is `T n` (redundant parentheses), returning `T`.
- `c`: an object initialized with `T(1)`. `1` can't appear in a declarator, so it can't be a parameter declaration.
- `d`: an object; the extra outer parentheses mean it can't be a parameter-declaration-clause.
- `e`: a function with two parameters: `T n` and `T(*)()`.

Clang gives `-Wvexing-parse` warnings for `a`, `b` and `e`.
</details>

!!! question "Question 2"
    With `template<int N> struct Y {};`, `Y<int()>` is ill-formed. What about `Y<(int())>`?

<details markdown="1">
<summary>Answer</summary>

It is well-formed and equals `Y<0>`. A type-id can't start with `(`, so in a template argument position `(int())` can only be an expression. It is a parenthesized expression, and the inside of a parenthesized expression `( expression )` only accepts an expression, with no type-id option. The only construct that puts a type in parentheses is the C-style cast `( type ) cast-expression`, and here `)` is immediately followed by `>`, which can't form a cast. So `int()` is an expression with value 0. Clang 23 accepts this form.
</details>
