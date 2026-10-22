---
title: Value category
summary: "Every expression belongs to exactly one of lvalue, xvalue and prvalue; a prvalue's result object is provided by its context; which conversions are inserted when an operator needs a different category; through glvalues of which types an object may be accessed (strict aliasing)."
updated: 2026-10-19
---

!!! tldr
    - Every expression belongs to exactly one of three value categories: an lvalue designates an object or function, an xvalue designates an object whose resources can be taken, and a prvalue designates no object; it only initializes an object or computes a value.
    - A named rvalue reference variable is an lvalue as an expression; only unnamed rvalue references such as `std::move(x)` are xvalues.
    - The context decides which object a prvalue initializes (its result object), so `T x = T();` has just one object, and since C++17 no copy or move constructor is needed.
    - When an operator wants a prvalue and the operand is a glvalue, its value is read automatically; when it wants an object and the operand is a prvalue, a temporary object is materialized automatically.
    - An object may only be accessed through a glvalue of a similar type, the corresponding signed/unsigned type, or `char`/`unsigned char`/`std::byte`; otherwise it is UB. This is the strict aliasing rule.

## The three value categories (¶1–¶3)

```cpp ok
#include <utility>
#include <string>
std::string make();

void demo(std::string s, std::string&& rr) {
    std::string a = s;              // s is an lvalue: copy
    std::string b = std::move(s);   // std::move(s) is an xvalue: move
    std::string c = make();         // make() is a prvalue: initializes c directly, no copy or move
    std::string d = rr;             // rr is an lvalue (although declared as an rvalue reference): copy
}
```

Each line initializes a variable from a `std::string` expression, yet the four lines all behave differently. What decides the behavior is the expression's **value category**, the second static property every expression has besides its type.

¶1 The standard uses a figure to divide expressions into five categories, three of which are primary:

```text
            expression
           /          \
      glvalue        rvalue
      /     \        /    \
  lvalue     xvalue      prvalue
```

- **glvalue**: an expression whose evaluation determines the identity of an object, function, non-static data member or direct base class relationship. Determining identity means the result of evaluation is a definite entity: you can take its address and compare it with other entities to see whether they are the same.
- **prvalue**: an expression whose evaluation initializes an object or computes the value of an operand of an operator; an expression of type cv `void` is also a prvalue.
- **xvalue**: a glvalue that denotes an object whose resources can be reused, usually because it is near the end of its lifetime.
- **lvalue**: a glvalue that is not an xvalue.
- **rvalue**: a prvalue or an xvalue.

¶2 Every expression belongs to exactly one of lvalue, xvalue and prvalue. The subclause for each built-in operator says what category it requires of its operands and what category its result is; for example, built-in assignment requires its left operand to be an lvalue, and its result is also an lvalue. User-defined operators are functions, and their categories are determined by the parameter and return types.

The three primary categories can be seen as combinations of two properties:

| | Resources can be taken | Resources can't be taken |
|---|---|---|
| Has identity | xvalue | lvalue |
| No identity | prvalue | (doesn't exist) |

Those with identity are glvalues; those whose resources can be taken are rvalues. C++11 introduced xvalues precisely to fill the top-left cell: move semantics needs an expression that designates an existing object but lets others take its resources.

¶3 The note explains where the names come from: lvalues and rvalues were originally expressions that could appear on the left and right of an assignment, which has long been inaccurate (a `const int` variable is an lvalue but can't be assigned to). glvalue is "generalized lvalue", prvalue is "pure rvalue", and xvalue is "eXpiring value". These terms describe expressions, not values.

!!! note "Non-static data members and direct base class relationships"
    These two items in the definition of glvalue were added for C++26 static reflection. A splice expression `[: r :]` is an lvalue designating the member when `r` reflects a non-static data member ([[expr.prim.splice]]), and in `obj.[: r :]` `r` can also reflect a direct base class relationship, in which case the result designates the corresponding base class subobject ([[expr.ref]]).

## Which expressions are xvalues (¶4)

¶4 is a note that lists every form that yields an xvalue:

| Form | Example |
|---|---|
| A move-eligible *id-expression* or splice expression ([[expr.prim.id.unqual]]) | `x` in `return x;` (where `x` is a local object) |
| A call to a function whose return type is an rvalue reference to object type ([[expr.call]]) | `std::move(x)`, and `f()` for `A&& f();` |
| A cast to an rvalue reference to object type | `static_cast<A&&>(a)`, `(A&&)a` |
| A subscripting operation with an xvalue array operand ([[expr.sub]]) | `std::move(arr)[0]` |
| A class member access where the object expression is an xvalue and the member is a non-static data member of non-reference type ([[expr.ref]]) | `std::move(a).m`, `f().m` |
| A `.*` whose first operand is an xvalue and whose second operand is a pointer to data member ([[expr.mptr.oper]]) | `std::move(a).*pm` |

The note concludes: named rvalue references are lvalues; unnamed rvalue references to objects are xvalues; rvalue references to functions are lvalues whether named or not.

```cpp ok
#include <utility>
struct A { int m; };
A&& operator+(A, A);
A&& f();
A make();

void demo(A a) {
    A&& ar = static_cast<A&&>(a);
    // xvalue: f(), f().m, static_cast<A&&>(a), a + a, std::move(a), make().m
    // lvalue: ar, a, a.m
    // prvalue: make()
    A b = ar;               // copy construction: ar is an lvalue
    A c = std::move(ar);    // move construction: std::move(ar) is an xvalue
    (void)b; (void)c;
}
```

`make().m` is an xvalue. `make()` is a prvalue and member access needs an object, so it is first materialized as a temporary object (see below), giving an xvalue; a non-reference member of an xvalue is also an xvalue.

Functions have no resources to take, and there are no temporary functions, so expressions designating functions are always lvalues. `decltype((std::move(f)))` is `void(&)()`, not `void(&&)()`.

## Results and result objects (¶5)

¶5 The **result** of a glvalue is the entity it denotes. The result of a prvalue is the value it stores into its context; the **result object** ([[g:result-object]]) of a prvalue is the object it initializes. A prvalue of type cv `void` has neither a result nor a result object.

Note 4 adds: except when it is the operand of `decltype`, a prvalue of object type always has a result object; if the context doesn't provide one, a temporary object is materialized.

So since C++17, a prvalue is not an object but a way of initializing some object. That object is provided by the context:

| Context | Result object |
|---|---|
| `T x = prvalue;`, `T x(prvalue);`, `T x{prvalue};` (same type) | The variable `x` itself ([[dcl.init.general]]) |
| `return prvalue;` (same type) | The result object of the caller's function call expression |
| Argument for a by-value parameter `f(prvalue)` | The parameter object |
| `new T(prvalue)` | The dynamically allocated object |
| `const T& r = prvalue;`, `prvalue.m`, a discarded `prvalue;` | A materialized temporary object |

```cpp run title="no-copy.cpp" ok
struct NonMovable {
    NonMovable() = default;
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable{}; }  // the prvalue directly initializes the caller's object

int main() {
    NonMovable a = make();                   // a is the result object of make()
    NonMovable b = NonMovable(NonMovable()); // only one object, b
    (void)a; (void)b;
}
```

There is nothing to copy anywhere in this code, so it doesn't matter that the copy and move constructors are deleted. In C++14 all three places were ill-formed, because back then a copy or move constructor had to be accessible even when the copy was elided.

Named objects are different. In `NonMovable x; return x;`, `x` is an existing object that has to be moved on return (NRVO is only permitted, not guaranteed), so a usable move constructor is required; see [[class.copy.elision]].

## When an operator needs a different category (¶6, ¶7)

### A glvalue becomes a prvalue (¶6)

¶6 When a glvalue appears as an operand where a prvalue is expected, one of three standard conversions is applied automatically:

- an ordinary object: the lvalue-to-rvalue conversion ([[conv.lval]]), i.e. its value is read;
- an array: the array-to-pointer conversion ([[conv.array]]);
- a function: the function-to-pointer conversion ([[conv.func]]).

```cpp ok
struct S { unsigned bits : 3; };
const int ci = 41;

int use(S s) {
    int a = ci + 1;     // ci is an lvalue of const int; once read, it is a prvalue of int
    auto b = s.bits;    // b has type unsigned (the declared type of the bit-field)
    auto c = +s.bits;   // c has type int: read, then integral promotion
    return a + b + c;
}
```

¶6 comes with three notes:

- Note 5: binding an rvalue reference to an lvalue is not such a context. `int&& r = x;` does not read the value of `x` and then materialize a temporary; it is simply ill-formed ([[dcl.init.ref]]).
- Note 6: on conversion to a prvalue, cv-qualifiers of non-class types are removed, so an lvalue of `const int` can be used where a prvalue of `int` is required.
- Note 7: there are no prvalue bit-fields. Reading a bit-field gives an ordinary prvalue of the bit-field's declared type, which may then undergo integral promotion ([[conv.prom]]). `unsigned bits : 3` is promoted to `int` in arithmetic because `int` can represent all values of a 3-bit unsigned number.

### A prvalue becomes an xvalue (¶7)

¶7 Except where [[expr.reinterpret.cast]] and [[expr.const.cast]] specify otherwise, whenever a prvalue that is not the result of the lvalue-to-rvalue conversion appears as an operand of an operator, the **temporary materialization conversion** ([[g:temporary-materialization-conversion]], [[conv.rval]]) is applied to it, turning it into an xvalue designating a temporary object.

```cpp ok
#include <string>
struct P { int m; int get() const { return m; } };
P make();

char first = std::string("abc")[0];   // materialize a std::string temporary, then subscript
int  v = make().m + make().get();     // two P temporaries
```

Operators such as `.` and `[]` need an object, and a prvalue is not an object, so it is materialized first. A prvalue that is not an operand of an operator is not materialized, for example as the initializer of a variable of the same type or the operand of `return`; that is exactly why the previous section had no copies.

!!! lawyer "Does `1 + 2` materialize too?"
    Read literally, `1` and `2` are both prvalue operands that don't come from the lvalue-to-rvalue conversion, so they are first materialized as temporary objects (xvalues); `+` needs prvalues, so per ¶6 their values are then read. What's read is the result of the lvalue-to-rvalue conversion, so ¶7 no longer applies and there is no loop. The upshot is that every value an operator reads comes from some object. For scalars this is unobservable, and implementations don't actually allocate storage. The C++17 wording only materialized where a glvalue was needed in the operand position; the current draft extends this to all operator operands.

¶8 is a note pointing out that the behavior of lvalues and rvalues in reference initialization ([[dcl.init.ref]]) and for temporary objects ([[class.temporary]]) is described by those two subclauses.

## Restrictions on types (¶9, ¶10)

### Completeness and cv (¶9)

¶9 Except as the operand of `decltype` ([[dcl.type.decltype]]), a prvalue must have a complete type or `void`; if it has class type or array of class type, the class must not be abstract ([[class.abstract]]). A glvalue must not have type cv `void`.

Note 9 adds: a glvalue may have an incomplete non-`void` type, such as `arr` in `extern int arr[];`. Class and array prvalues can be cv-qualified; all other prvalues are never cv-qualified ([[expr.type#2]]).

```cpp ok
#include <type_traits>
struct A {};
const A   h();    // h() is a prvalue of type const A
const int g();    // the type of g() is adjusted to int

static_assert(std::is_same_v<decltype(h()), const A>);
static_assert(std::is_same_v<decltype(g()), int>);

struct Incomplete;
Incomplete make_inc();
using T = decltype(make_inc());   // the operand of decltype need not have a complete type
```

Class prvalues keep cv because member functions can be called on them, and `const` affects overload resolution. This has a side effect: in `x = h();` the right operand is a prvalue of `const A`, the parameter of `A::operator=(A&&)` can't bind to it, and only copy assignment can be chosen. So returning by `const` value gets in the way of moves.

```cpp error
struct Abstract { virtual void f() = 0; };
Abstract make_abs();          // only a declaration: since C++20 not checked here
void use() { make_abs(); }    // error: a prvalue can't have abstract class type
```

!!! impl "What Clang misses"
    At the time of writing, Clang 23 accepts the call to `make_abs()` above (it even accepts `auto&& r = make_abs();`) without a diagnostic. Per ¶9 this is ill-formed, and the call can't be implemented anyway, since an abstract class can't have complete objects.

### Modifiable lvalues (¶10)

¶10 An lvalue is **modifiable** if its type is not `const`-qualified and is not a function type. A program that attempts to modify an object through a nonmodifiable lvalue or through an rvalue is ill-formed ([[expr.assign]], [[expr.pre.incr]], [[expr.post.incr]]). This restriction is about built-in operators; assignment of class types is a function call and isn't affected.

<div class="compare" markdown="1">

```cpp error
const int c = 0;
int f();
void demo() {
    c = 1;     // error: not modifiable
    f() = 1;   // error: not an lvalue
}
```

```cpp ok
#include <string>
void demo() {
    // calls std::string::operator=
    // on a temporary object
    std::string() = "ok";
}
```

</div>

## Strict aliasing: through which types an object may be accessed (¶11)

```cpp run title="tbaa.cpp" ub
#include <cstdio>
int f(int* i, float* fp) {
    *i = 1;
    *fp = 2.0f;     // the compiler assumes *fp can't be *i
    return *i;      // so it returns the constant 1 directly
}

int g(int* i, unsigned* u) {
    *i = 1;
    *u = 2;         // unsigned can alias int: *i must be read again
    return *i;
}

int main() {
    int x;
    std::printf("%x\n", f(&x, reinterpret_cast<float*>(&x)));  // UB: modifies an int object through a float lvalue
}
```

At `-O2`, Clang 23 compiles `f` into two stores followed by returning 1 directly, while `g` reads `*i` again after the second store. In our tests this program prints `40000000` (the bit pattern of 2.0f) at `-O0` and `1` at `-O2`. The compiler's license for this is ¶11.

¶11 first defines a term. An object of dynamic type `Tobj` is **type-accessible** ([[g:type-accessible]]) through a glvalue of type `Tref` if `Tref` is similar to one of:

1. `Tobj` itself;
2. the signed or unsigned type corresponding to `Tobj`;
3. `char`, `unsigned char` or `std::byte`.

If the stored value of an object is accessed (read or written, [[defns.access]]) through a glvalue through which it is not type-accessible, the behavior is undefined.

!!! std
    If a program attempts to access the stored value of an object through a glvalue through which it is not type-accessible, the behavior is undefined.

Item by item:

1. **Similar** ([[g:similar-types|similar]], [[conv.qual]]) roughly means the two types are the same once cv-qualifiers at every level are removed and array bounds are ignored. So reading an `int` object through an lvalue of `const int`, or an `int**` object through `int* const*`, is fine.
2. An `int` object can be accessed through a glvalue of `unsigned int`, and vice versa. [[conv.lval]] specifies that the value read is the congruent value: `-1` reads as `UINT_MAX`.
3. Glvalues of `char`, `unsigned char` and `std::byte` can access any object; byte-level operations such as `memcpy`, serialization and hashing rely on this item. `signed char` is not included, and neither is `char8_t`.

The footnote says that the purpose of this list is to specify the circumstances in which an object may or may not be aliased. Conversely, the compiler may assume that two glvalues whose types don't meet these conditions don't refer to the same object; this is called type-based alias analysis (TBAA).

### Type punning done right

```cpp run title="punning.cpp" ok
#include <bit>
#include <cstdio>
#include <cstring>

int main() {
    float f = 1.0f;

    unsigned a = std::bit_cast<unsigned>(f);          // the preferred way since C++20
    unsigned b; std::memcpy(&b, &f, sizeof f);        // the classic way; compilers optimize it into a single move

    auto* bytes = reinterpret_cast<const unsigned char*>(&f);
    unsigned char first = bytes[0];                   // unsigned char can access any object

    int i = -1;
    unsigned u = *reinterpret_cast<unsigned*>(&i);    // the corresponding unsigned type

    std::printf("%x %x %u %u\n", a, b, first, u);
}
```

!!! pitfall "Type punning through a union is UB in C++"
    C allows writing one union member and reading another. C++ doesn't: reading an inactive member reads an object that is not within its lifetime ([[class.union]], [[basic.life]]). GCC guarantees the behavior of this pattern as an extension, but it is not portable C++.

!!! pitfall "`std::int8_t` and `char8_t` can't alias everything"
    `std::uint8_t` is usually an alias for `unsigned char`, so it happens to work; `std::int8_t` is usually `signed char`, so it doesn't. `char8_t` is a distinct type, and C++20 deliberately didn't give it aliasing power, so that compilers can optimize UTF-8 string processing.

### Copying class types and unions

Only glvalues of scalar type can access objects (the note in [[defns.access]]). Copying a class object calls a constructor or assignment operator; those calls themselves are not accesses, but the reads and writes of scalar subobjects inside them are, and each is subject to ¶11. Note 11 contrasts this with C: C can access a struct object as a whole through an lvalue of struct type, while C++ has no notion of accessing a class object through an lvalue of class type.

This leaves a gap: a union's defaulted copy and move copy the object representation as a whole (they don't know which member is active), with no scalar access at all. So ¶11 ends with a dedicated sentence: if a defaulted copy or move constructor or copy or move assignment operator of a union `U` is invoked with a glvalue argument that does not denote an object of type cv `U` within its lifetime, the behavior is undefined.

```cpp ub
union U { int i; float f; };

void copy_from_raw(void* raw) {
    U u = *static_cast<U*>(raw);   // raw doesn't point to a U object: UB
    (void)u;
}

int main() {
    double d = 0;
    copy_from_raw(&d);
}
```

## From the implementation side

!!! impl
    - Value categories don't exist at the ABI level. `T&` and `T&&` parameters are both passed as pointers in the Itanium ABI; only the mangled names differ (`f(int&&)` mangles as `_Z1fOi`, `f(int&)` as `_Z1fRi`). Value categories only affect compile-time overload resolution and semantic checks.
    - When a class type returned by value can't go in registers, the Itanium ABI has the caller pass the address of a block of storage, and the callee constructs the return value directly in it. This is what "the context provides a prvalue's result object" looks like at the machine level; C++17's guaranteed copy elision wrote this long-standing implementation technique into the semantics.
    - Clang attaches `!tbaa` metadata to every load and store in LLVM IR; the `char` family sits near the root of the type tree, so it can alias every type. `-fno-strict-aliasing` turns these optimizations off (the Linux kernel is compiled this way), and Clang's `-fsanitize=type` can detect some violations at run time.

## History

!!! history
    - C++98/03 had only two categories, lvalue and rvalue. Rvalues of class type could have member functions called on them and could be cv-qualified (non-lvalues in C are never qualified), so they were already somewhat object-like.
    - For rvalue references and move semantics, C++11 needed an expression that has identity and whose resources can be taken. [[N3055]] introduced xvalue, glvalue and prvalue, giving today's taxonomy.
    - C++17's [[P0135R1]] redefined a prvalue as a way of initializing an object, introducing result objects and temporary materialization; initializing an object of the same type from a prvalue no longer involves a copy. The same year `std::byte` was added to the aliasing list ([[P0298R3]]).
    - C++20's [[P1825R0]] and C++23's [[P2266R3]] extended and simplified implicit move. Since C++23, a move-eligible `x` in `return x;` is itself an xvalue.
    - The early aliasing list also had items such as an aggregate or union type that includes one of the above types among its members, and a type that is a base class type of the dynamic type of the object. C++ has no access to class objects, so these items were later removed; the current draft rephrases the rule using the term type-accessible and adds the rule about defaulted union copies.

## Common misconceptions

!!! pitfall "A variable of rvalue reference type is an rvalue"
    In `void f(std::string&& s)`, the expression `s` is an lvalue of type `std::string` (the reference was removed by [[expr.type]]). To keep passing it along as an rvalue, you must write `std::move(s)`. The value category is a property of the expression, and is a different thing from the variable's declared type.

!!! pitfall "`std::move` moves the object"
    `std::move` is just a `static_cast` to `T&&`, producing an xvalue; it does nothing by itself. What actually moves is the move constructor or move assignment operator that overload resolution then selects. If the type has no move constructor, or the object is `const`, it is copied anyway after `std::move`.

!!! pitfall "A prvalue is a temporary object"
    Since C++17 a prvalue is not an object. `T{}` by itself doesn't create a temporary object; one is materialized only when an object is needed and the context doesn't provide one (binding a reference, member access, discarding, and so on).

## Questions

!!! question "Question 1"
    Given `struct A { int m; int& r; static int s; };` and `A make();`, what are the value categories of `make().m`, `make().r` and `make().s`?

<details markdown="1">
<summary>Answer</summary>

- `make().m` is an xvalue: `make()` is materialized as an xvalue, and a non-static data member of non-reference type has the same category as the object expression ([[expr.ref]]).
- `make().r` is an lvalue: accessing a reference member always gives an lvalue, designating the object the reference is bound to, which has nothing to do with the temporary.
- `make().s` is an lvalue: accessing a static data member always gives an lvalue.

`decltype((make().m))` and the others are `int&&`, `int&` and `int&` respectively, which you can check with `static_assert`.
</details>

!!! question "Question 2"
    Is `int& f(int&& x) { return x; }` well-formed in C++20? In C++23?

<details markdown="1">
<summary>Answer</summary>

In C++20 it is well-formed: `x` is an lvalue and can bind to `int&`.

In C++23 it is ill-formed. After [[P2266R3]], `x` in `return x;` is move-eligible and is an xvalue, which can't bind to a non-`const` lvalue reference. This is a deliberate breaking change: returning an lvalue reference bound to an rvalue reference parameter almost always dangles.
</details>

!!! question "Question 3"
    On a platform where `long` and `long long` are both 64 bits, is it valid to read a `long long` object through a glvalue of `long`?

<details markdown="1">
<summary>Answer</summary>

It is UB. Type-accessibility looks only at types, not representations. `long` and `long long` are different types; they are neither similar nor each other's corresponding signed or unsigned type. Compilers really do exploit this: Clang at `-O2` compiles `long f(long* a, long long* b) { *a = 1; *b = 2; return *a; }` into returning 1 directly.
</details>
