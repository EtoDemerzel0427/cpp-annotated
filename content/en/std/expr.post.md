---
title: Postfix expressions
summary: "The syntax and grouping of postfix operators; built-in E1[E2] is just *((E1)+(E2)), and an array operand decides whether the result is an lvalue or an xvalue; C++23 multidimensional subscripts; the result, side effect and evaluation order of postfix ++/--."
updated: 2026-10-19
---

!!! tldr
    - Postfix operators are the tightest-binding layer and group left to right: `a.b[c](d)` is `((a.b)[c])(d)`, `*p++` is `*(p++)`.
    - Built-in subscripting `E1[E2]` is by definition `*((E1)+(E2))`, so it can be swapped to `2[a]`, and every restriction of pointer arithmetic applies.
    - With an array operand, the subscript result is an lvalue if the array is an lvalue and an xvalue otherwise; with a pointer operand it is always an lvalue.
    - Since C++17 the expression before the brackets is evaluated before the one inside; since C++23 `a[i, j]` is two arguments, no longer a comma expression.
    - The result of postfix `++` is a prvalue of the old value; `i = i++` is defined since C++17, while `i++ + i++` is still UB.

Postfix expressions include `a[b]`, `f(x)`, `T(x)`, `a.b`, `a->b`, `a++`, `a--`, the four named casts and `typeid`. This page covers the syntax of this layer ([[expr.post.general]]), subscripting ([[expr.sub]]) and postfix increment and decrement ([[expr.post.incr]]). For function calls, member access and functional casts see [[expr.call]], [[expr.ref]] and [[expr.type.conv]]; for the casts see the map in [[expr.compound]].

## Syntax and grouping [expr.post.general]

¶1 Postfix expressions group left to right. The grammar alternatives are:

```text
postfix-expression:
    primary-expression
    postfix-expression [ expression-list(opt) ]
    postfix-expression ( expression-list(opt) )
    simple-type-specifier ( expression-list(opt) )      // functional cast
    typename-specifier ( expression-list(opt) )
    simple-type-specifier braced-init-list
    typename-specifier braced-init-list
    postfix-expression . template(opt) id-expression
    postfix-expression . splice-expression
    postfix-expression -> template(opt) id-expression
    postfix-expression -> splice-expression
    postfix-expression ++
    postfix-expression --
    dynamic_cast < type-id > ( expression )            // and static_cast etc.
    typeid ( expression )
    typeid ( type-id )
```

A few things can be read straight off the grammar:

- The brackets of subscripting and calls contain an *expression-list*, i.e. an *initializer-list*, so braced lists and pack expansions can appear: `f({1, 2})`, `f(args...)`, `m[is...]`.
- The type part of a functional cast can only be a single type name; `unsigned int(x)` and `int*(p)` can't be written ([[expr.type.conv]]).
- `.` and `->` can be followed by a *splice-expression* {{c++26}}, as in `obj.[: r :]` ([[expr.ref]]).
- The four named casts and `typeid` are in the same layer as function calls; the C-style `(T)e` belongs to the looser *cast-expression* ([[expr.cast]]).

Because of left-to-right grouping, chains apply one after another from the left: `p->q++` is `(p->q)++`, and `f()[0]` calls first and then subscripts.

¶2 is a note: the `>` after the *type-id* in a named cast can come from splitting a `>>` ([[temp.names]]). So since C++11, `static_cast<std::vector<int>>(v)` doesn't need to be written with `> >`.

## Subscripting [expr.sub]

### The part before the brackets is evaluated first (¶1)

```cpp run title="sub-order.cpp" ok
#include <cstdio>

int* arr() { std::puts("arr"); static int a[4]{}; return a; }
int idx() { std::puts("idx"); return 1; }

int main() {
    arr()[idx()] = 42;   // guaranteed since C++17: prints arr, then idx
    idx()[arr()] = 7;    // the swapped form is also valid; idx before the brackets is still evaluated first
}
```

¶1 A postfix expression followed by a possibly empty, comma-separated list of *initializer-clause*s in square brackets is a [[g:subscript-expression|subscript expression]]. The items in the list are the arguments of the subscript operator. Multiple or zero arguments are meaningful only for an overloaded `operator[]`.

The evaluation order rule is: the postfix expression before the brackets, and for an overload the initialization of the object parameter, is sequenced before each expression in the brackets and each default argument. The initializations of the non-object parameters of an overloaded `operator[]` are [[g:indeterminately-sequenced|indeterminately sequenced]] with respect to each other, i.e. one comes before the other but which one is not specified, consistent with function calls ([[expr.call#8]]).

Before C++17, `E1` and `E2` were unsequenced, making code like `m[k()] = v()` hard to reason about. The C++17 evaluation-order proposal [[P0145R3]] sequenced `E1` before `E2`; once multiple arguments were added, the rule was rewritten into the form above.

### Built-in subscripting is pointer addition plus indirection (¶2)

¶2 Built-in subscripting requires exactly one *assignment-expression* in the brackets. One of the two operands is a glvalue of type "array of `T`" or a prvalue of type "pointer to `T`", and the other is a prvalue of integral or unscoped enumeration type. The result has type `T`, which must be a completely-defined object type; a footnote says this holds even in a form that only takes the address, such as `&x[0]`.

!!! std
    The expression `E1[E2]` is identical (by definition) to `*((E1)+(E2))`, except that in the case of an array operand, the result is an lvalue if that operand is an lvalue and an xvalue otherwise.

Subscripting is not an operation of its own but pointer addition ([[expr.add]]) plus unary `*` ([[expr.unary.op]]). The rules of pointer arithmetic therefore apply to subscripting unchanged: you can only move within the same array object, and you may form a past-the-end pointer but not access through it.

```cpp title="sub-errors.cpp" error
struct Incomplete;
extern Incomplete* pi;
int a[3];
enum class Color { red };

void f() {
    a[{1}];          // error: built-in subscripting can't take a braced list
    a[1, 2];         // error: built-in subscripting takes exactly one argument (since C++23)
    a[Color::red];   // error: scoped enumerations don't convert implicitly to integers
    &pi[0];          // error: T must be complete, even just to take the address
    a[1.0];          // error: the subscript must be integral or unscoped enumeration
}
```

`a[1.0]` doesn't convert `1.0` to an integer. ¶2 only accepts operands of integral or unscoped enumeration type, and `a + 1.0` is itself ill-formed in [[expr.add]].

### Lvalue or xvalue result

Expanding literally as `*((E1)+(E2))`, the array would first be converted to a pointer ([[conv.array]]), and the result of `*` is always an lvalue, so the information that the array itself is about to expire would be lost. So ¶2 makes a special provision for array operands: if the array is an lvalue, the result is an lvalue; if the array is an xvalue, so is the result. This is consistent with member access, where `std::move(s).m` is also an xvalue ([[expr.ref#8]]).

```cpp run title="sub-category.cpp" ok
#include <type_traits>
#include <utility>

struct S { int arr[3]; };
int a[3];
int* p = a;
using A = int[3];

static_assert(std::is_same_v<decltype((a[0])), int&>);              // lvalue array → lvalue
static_assert(std::is_same_v<decltype((std::move(a)[0])), int&&>);  // xvalue array → xvalue
static_assert(std::is_same_v<decltype((S{}.arr[0])), int&&>);       // array member of a temporary → xvalue
static_assert(std::is_same_v<decltype((A{1, 2, 3}[0])), int&&>);    // array prvalue is materialized first → xvalue
static_assert(std::is_same_v<decltype((std::move(p)[0])), int&>);   // pointer operand: always an lvalue

int main() {}
```

In the last line, `std::move(p)` is an xvalue pointer, but it is the pointer that is about to expire, which has nothing to do with the object it points to, so the result is still an lvalue. In the `A{1, 2, 3}[0]` line, the array operand must be a glvalue and `A{1, 2, 3}` is a prvalue, so the [[g:temporary-materialization-conversion|temporary materialization conversion]] ([[conv.rval]]) is applied first to get an xvalue.

### Subscripting is commutative (¶3)

¶3 is a note: subscripting looks asymmetric, but apart from evaluation order it is commutative. In `E1 + E2` the pointer and the integer can be on either side, so `a[2]`, `2[a]` and `*(a + 2)` are fully equivalent.

```cpp run title="commutative.cpp" ok
int main() {
    int a[] = {10, 20, 30};
    char c = 1["abc"];         // 'b': a string literal is an array lvalue
    int x = 2[a];              // equivalent to a[2]
    return (x == 30 && c == 'b') ? 0 : 1;
}
```

"Apart from evaluation order" refers to ¶1: the operand before the brackets is always evaluated first, whether it is the array or the index.

### Is `&a[N]` valid?

`int a[N]; int* end = &a[N];` is common, and by definition it is `&*(a + N)`. `a + N` is a valid past-the-end pointer; the problem is the `*`. The current draft's [[expr.unary.op#1]] says: if the operand points to an object or function, the result denotes it; otherwise the behavior is undefined. A past-the-end pointer doesn't point to any object, so under the current draft `&a[N]` is UB. C explicitly says `&*p` doesn't evaluate the `*`; C++ has no corresponding exemption.

In practice, mainstream compilers all treat `&a[N]` as `a + N`. Clang 23 even accepts `constexpr const int* e = &a[3];` in a constant expression (with `a` having 3 elements), rejecting only a read of `a[3]`; under the draft this should be diagnosed. To avoid the controversy, write `a + N` or `std::end(a)`.

### C++23: multidimensional subscripts

Before C++20, the comma in `a[i, j]` was the comma operator, and the whole expression was `a[j]`. That was almost always a bug, and it prevented `operator[]` from taking multiple arguments.

| Version | Meaning of `a[i, j]` |
|---|---|
| C++98–17 | Comma expression, i.e. `a[(i, j)]` |
| C++20 | Still a comma expression, but a top-level comma expression in brackets is deprecated {{deprecated}} ([[P1161R3]]) |
| Since C++23 | Two arguments: ill-formed for built-in subscripting, calls `a.operator[](i, j)` for class types ([[P2128R6]]) |

[[diff.cpp20.expr]] lists this as an incompatibility with C++20. When you really need the comma operator, add parentheses: `a[(i, j)]`.

Correspondingly, [[over.sub]] allows `operator[]` to have any number of parameters (including zero) and default arguments; C++23 also allows it to be a static member function ([[P2589R1]]). `std::mdspan` uses multidimensional subscripts.

```cpp run title="multi-subscript.cpp" ok
#include <cstddef>

struct Matrix {
    double data[3][4]{};
    double& operator[](std::size_t i, std::size_t j) { return data[i][j]; }
};

struct Table {
    static int operator[](int i) { return i * i; }    // static operator[]
};

int main() {
    Matrix m;
    m[1, 2] = 3.5;                 // m.operator[](1, 2)
    int a[5]{};
    int k = 0;
    a[(k++, 4)] = 1;               // comma expression in parentheses, i.e. a[4]
    return (m[1, 2] == 3.5 && Table{}[3] == 9 && a[4] == 1 && k == 1) ? 0 : 1;
}
```

## Postfix increment and decrement [expr.post.incr]

### Result and side effect (¶1)

```cpp run title="post-incr.cpp" ok
int main() {
    int i = 5;
    int old = i++;                // old == 5, i == 6
    double d = 1.5; d++;          // floating point works too
    int a[3]{}; int* p = a; p++;  // the pointer advances by one element
    return (old == 5 && i == 6 && d == 2.5 && p == a + 1) ? 0 : 1;
}
```

¶1 The rules for postfix `++` can be understood in this order:

1. The operand must be a modifiable lvalue ([[basic.lval#10]]) of arithmetic type other than cv `bool`, or a pointer to a complete object type.
2. The value of the expression is obtained by applying the lvalue-to-rvalue conversion ([[conv.lval]]) to the operand. Note 1 says this is a copy of the original value.
3. The operand object is modified as if it were the operand of prefix `++` ([[expr.pre.incr]]): numbers are incremented by 1, pointers advance by one element.
4. The value computation is sequenced before the modification.
5. With respect to an indeterminately-sequenced function call, the whole postfix `++` operation is a single evaluation.
6. The result is a prvalue whose type is the cv-unqualified version of the operand's type.

In addition, using an operand of volatile-qualified type is deprecated {{deprecated}} ([[depr.volatile.type]], C++20's [[P1152R4]]).

Item 5 together with Note 2 means a function call can't be interleaved between reading the old value and writing the new one. In `f(i++) + g()`, if `g` also reads and writes `i`, `g` sees either the `i` before the increment happened at all or the `i` after it happened completely, never an intermediate state that has been read but not yet written.

### Disallowed operands

```cpp title="post-incr-errors.cpp" error
struct Incomplete;
void g(Incomplete* pi, void* vp, void (*fp)()) {
    bool b = false;
    b++;            // error: bool can't be incremented since C++17
    const int c = 0;
    c++;            // error: not a modifiable lvalue
    5++;            // error: not an lvalue
    pi++;           // error: points to an incomplete type
    vp++;           // error: void* is not a pointer to an object type
    fp++;           // error: function pointers can't be incremented
    int i = 0;
    i++++;          // error: i++ is a prvalue and can't be incremented again
}
```

`++` on a `bool` set it to `true` in C++98; it was already deprecated then, and C++17 removed it through [[P0002R1]] {{removed:C++17}}; `--` on a `bool` was never allowed. GCC accepts `vp++` as an extension and warns with `-pedantic`. `++i++` is `++(i++)` and equally ill-formed; `(++i)++` is valid because the result of prefix `++` is an lvalue.

¶2 Postfix `--` decrements the operand by 1 in the same way. For the prefix versions see [[expr.pre.incr]].

### What is still UB

C++17's [[P0145R3]] added ordering for assignment, shifts, subscripting and member access, but the two operands of binary arithmetic operators such as `+` and `*` remain unsequenced:

```cpp title="incr-order.cpp"
void f(int, int);

void g() {
    int i = 0;
    i = i++;            // OK (since C++17): the right operand is sequenced before the assignment, i stays 0
    i = i++ + 1;        // OK (since C++17): i is 1
    int j = i++ + i++;  // UB: two modifications of the same scalar are unsequenced
    f(i++, i++);        // unspecified: the parameter initializations are indeterminately sequenced, not UB
    (void)j;
}
```

The last line is often mistaken for UB. Since C++17, the initializations of a function's parameters (together with the evaluation of their arguments) are indeterminately sequenced with respect to each other ([[expr.call#8]]): the two modifications happen one after the other, it is just unspecified which comes first. Clang 23 still reports `-Wunsequenced` (multiple unsequenced modifications) for this line; the wording is inaccurate under C++17, but it is still a useful warning.

### Overloaded postfix `++`

For class types, `a++` calls `operator++(int)` ([[over.inc]]); the `int` parameter only serves to distinguish it from the prefix version. The standard doesn't constrain the return value of the overload; by convention it returns a copy of the old value by value, consistent with the built-in version. Because it constructs an extra copy, iterator loops usually write `++it`.

## Common misconceptions

!!! pitfall "`*p++` changes the pointer"
    `*p++ = x` is `*(p++) = x`: it writes `x` to where `p` used to point, then advances `p`. To increment the pointed-to value, write `(*p)++` or `++*p`.

!!! pitfall "`a[i, j]` means different things in different standards"
    The same code accesses `a[j]` under C++17, gets a deprecation warning under C++20, and under C++23 is an error for built-in arrays and calls the new overload for classes with a multi-parameter `operator[]`. To stay compatible across versions, always parenthesize comma expressions in subscripts.

!!! pitfall "`std::move(v)[i]` moves the element"
    The xvalue rule only applies to built-in array operands. `std::vector::operator[]` has no `&&` overload, so `std::move(v)[i]` is still an lvalue and the element is not moved.

## Questions

!!! question "Question 1"
    Given `int a[2][3];`, what is `decltype((std::move(a)[1][2]))`?

<details markdown="1">
<summary>Answer</summary>

`int&&`. `std::move(a)` is an xvalue of `int[2][3]`; as an array operand, `std::move(a)[1]` is an xvalue of `int[3]`; that is again an array operand, so the result of `[2]` is also an xvalue, of type `int`. The xvalue-ness propagates down every dimension of the array.
</details>

!!! question "Question 2"
    Is `"abc"[3]` valid? What is its value? What about `&"abc"[4]`?

<details markdown="1">
<summary>Answer</summary>

`"abc"` has type `const char[4]`, including the terminating `'\0'`, so `"abc"[3]` is valid and is an lvalue of `'\0'`. `"abc" + 4` is a past-the-end pointer and valid; `&"abc"[4]` is `&*("abc" + 4)`, and by the current draft's [[expr.unary.op#1]], applying `*` to a pointer that doesn't point to an object is UB, just like `&a[N]` above; in practice compilers treat it as `"abc" + 4`. `"abc"[5]` is already out of bounds even as a pointer, and is UB.
</details>

!!! question "Question 3"
    Given `struct S { int operator[](int) &&; }; S s;`, which of `S{}[0]` and `s[0]` is valid? How does this relate to the xvalue rule for built-in arrays?

<details markdown="1">
<summary>Answer</summary>

`S{}[0]` is valid: `S{}` is a prvalue and can bind to the `&&`-qualified implicit object parameter. `s[0]` is ill-formed: an lvalue can't bind to `&&`. An overloaded `operator[]` uses ref-qualifiers to distinguish subscripting an expiring object, while for built-in arrays ¶2 directly says the result is an xvalue; both express the same intent.
</details>
