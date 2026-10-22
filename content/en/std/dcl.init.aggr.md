---
title: Aggregates
summary: "Which types are aggregates, and how aggregate initialization distributes the clauses in braces among the elements: brace elision, designated initializers, elements not mentioned, arrays of unknown bound, and unions."
updated: 2026-10-19
---

!!! tldr
    - An aggregate is an array, or a class with no user-declared constructors, no private or protected direct data members or base classes, and no virtual functions or virtual base classes. Since C++20, writing `S() = default;` makes a class no longer an aggregate.
    - Aggregate initialization doesn't call the aggregate's own constructor; it hands the clauses in the list to the elements in order. The elements are the direct base classes plus the direct non-static data members.
    - When a clause neither starts with `{` nor can be converted to the current element's type, initialization descends into that subaggregate; this is brace elision.
    - Elements not mentioned use their default member initializers, or else are copy-initialized from `{}`; a reference member not mentioned is ill-formed.
    - Designated initializers `.x = 1` can only be used for classes, must be in declaration order, can't be nested and can't repeat.

## What an aggregate is (¶1)

```cpp
struct Point { int x, y; };
Point p = {1, 2};       // no constructor call: p.x = 1, p.y = 2
int a[3] = {1, 2};      // a[2] is initialized from {}, i.e. 0
```

An **aggregate** ([[g:aggregate|aggregate]]) is a kind of simple data collection inherited from C. Aggregate initialization doesn't go through the aggregate's own constructor; it hands initializers to each element one by one from outside.

¶1 An aggregate is an array, or a class that satisfies four conditions:

- ¶1.1 no user-declared or inherited constructors ([[class.ctor]]);
- ¶1.2 no private or protected direct non-static data members;
- ¶1.3 no private or protected direct base classes;
- ¶1.4 no virtual functions and no virtual base classes.

Each condition corresponds to a case where initializing one by one from outside doesn't work. A declared constructor means the author wants to control initialization, and bypassing it would break the class's invariants. Private members and private bases are inaccessible from outside. Virtual functions and virtual bases need construction to set up the vtable pointer and virtual base offsets.

Plenty is still allowed: public non-virtual bases, default member initializers, member functions, static members, user-declared destructors and assignment operators. The elements themselves can be classes with constructors: `struct S { std::string s; int n; };` is an aggregate, and `s` is still initialized by `std::string`'s constructor.

```cpp run ok
#include <type_traits>
struct A { int x; int y = 2; };          // an aggregate since C++14
struct Base { int b; };
struct D : Base { int d; };              // an aggregate since C++17
struct Del { Del() = delete; int x; };   // not an aggregate since C++20
static_assert(std::is_aggregate_v<A>);
static_assert(std::is_aggregate_v<D>);
static_assert(!std::is_aggregate_v<Del>);
D d{{1}, 2};                             // d.b == 1, d.d == 2
int main() {}
```

### Protected constructors of base classes

<div class="compare" markdown="1">

```cpp ok
struct B {
protected:
  B() = default;
  int x;
};
struct D : B {};
D d1;   // OK
```

```cpp error
struct B {
protected:
  B() = default;
  int x;
};
struct D : B {};
D d2{}; // error
```

</div>

`D` is an aggregate. `D d1;` is default-initialization, calling `D`'s implicit default constructor, which, as a member of the derived class, can access `B`'s protected constructor. `D d2{};` is aggregate initialization, which initializes the base class element `B` from `{}` at the point of `d2`'s declaration, where `B()` isn't accessible. Note 1 says exactly this: aggregate initialization can't access protected and private members of base classes, including constructors.

## Elements (¶2, ¶12)

¶2 The **elements** ([[g:aggregate-element|elements]]) of an aggregate are:

- ¶2.1 for an array, the array elements in increasing subscript order;
- ¶2.2 for a class, first the direct base classes in declaration order, then the direct non-static data members in declaration order, excluding members of anonymous unions.

The note in ¶12 adds that static data members and unnamed bit-fields are not elements. Members inside an anonymous union are not elements; the anonymous union itself, as a whole, is an element.

```cpp run ok
struct A {
  int i;
  static int s;   // not an element
  int j;
  int : 17;       // unnamed bit-field, not an element
  int k;
} a = { 1, 2, 3 };              // i = 1, j = 2, k = 3
static_assert(sizeof(A) > 0);
int main() { return a.k == 3 ? 0 : 1; }
```

## Which element a clause appertains to: brace elision (¶15–¶18)

```cpp run ok
struct S1 { int a, b; };
struct S2 { S1 s, t; };
S2 x[2] = { 1, 2, 3, 4, 5, 6, 7, 8 };   // all inner braces elided
S2 y[2] = { { { 1, 2 }, { 3, 4 } },
            { { 5, 6 }, { 7, 8 } } };   // fully braced; x and y have the same values
int main() { return x[1].t.b == y[1].t.b ? 0 : 1; }
```

Inner braces can be omitted; this is **brace elision** ([[g:brace-elision|brace elision]]). ¶15 describes it precisely with the notion of **appertaining** ([[g:appertain|appertain]]): each clause appertains to an element of the aggregate or to an element of some subaggregate.

¶15 aligns the sequence of clauses with a sequence of elements one by one. The element sequence starts as the elements of the aggregate being initialized. The current clause appertains to the current element if any of the following holds:

- ¶15.1 the current element is not an aggregate;
- ¶15.2 the clause starts with a left brace;
- ¶15.3 the clause is an expression that can be implicitly converted to the type of the current element;
- ¶15.4 the current element is an aggregate that itself has no elements.

If none holds, the current element must be a subaggregate, and the clause neither starts with `{` nor can be converted to it as a whole. In that case the subaggregate is replaced in the sequence by its own elements, and the same clause is checked again starting from the first subelement. The process ends when the clauses run out; if some clause has nothing left to appertain to, the program is ill-formed, as in `char cv[4] = { 'a', 's', 'd', 'f', 0 };`.

Clang gives a `-Wmissing-braces` warning for brace-elided forms, noting that they are hard to read, but the program is well-formed.

### If it converts, don't descend (¶18)

The third condition makes a clause prefer to appertain to the subaggregate itself. The example in ¶18:

```cpp run ok
#include <cassert>
struct A { int i; operator int() { return 7; } };
struct B { A a1, a2; int z; };
int main() {
  A a{5};
  B b = { 4, a, a };
  assert(b.a1.i == 4);   // 4 can't convert to A, so it descends into a1: b.a1.i = 4
  assert(b.a2.i == 5);   // a converts to A: b.a2 is copied from a, no descent
  assert(b.z == 7);      // the third a initializes b.z via operator int()
}
```

### An empty subaggregate takes a clause too (¶17)

The fourth condition makes an empty aggregate always consume a clause. So if more elements follow, an empty subaggregate must be given an initializer (the note in ¶17):

<div class="compare" markdown="1">

```cpp ok
struct Empty {};
struct D : Empty { int x; };
D d1{{}, 1};   // OK
```

```cpp error
struct Empty {};
struct D : Empty { int x; };
D d2{1};       // error: 1 appertains to
               // the empty base Empty
```

</div>

### Double braces for `std::array`

`std::array<T, N>` is an aggregate with a single `T[N]` member. `std::array<int, 3> a{{1, 2, 3}};` is the full form, and `a{1, 2, 3}` relies on brace elision. When the elements are themselves aggregates, the result can be surprising:

```cpp
#include <array>
struct Pt { int x, y; };
std::array<Pt, 2> ok{{ {1, 2}, {3, 4} }};   // OK
std::array<Pt, 2> bad{ {1, 2}, {3, 4} };    // error: too many initializers
```

In the outer list of `bad`, `{1, 2}` starts with `{`, so it appertains to the only element of `array`, the internal array `Pt[2]`. When the internal array is initialized from `{1, 2}`, `1` can't convert to `Pt`, so it descends into `[0]`; `1` and `2` go to `[0].x` and `[0].y`, and `[1]` is initialized from `{}`. The outer `{3, 4}` has no element left to appertain to, so the program is ill-formed.

## Explicitly initialized elements (¶4–¶5)

¶4 When an aggregate is list-initialized (the entry point is item 4 of [[dcl.init.list#3]]), the **explicitly initialized elements** ([[g:explicitly-initialized-element|explicitly initialized elements]]) are determined first:

- ¶4.2 in an ordinary list, the elements to which a clause appertains, or to whose subobjects one does;
- ¶4.1 in a designated list, the elements containing the designated members (see the next section);
- ¶4.3 no other elements. Note 2 points out that `{}` explicitly initializes no elements.

¶5.3 For an ordinary list, if a clause appertains directly to an element, that element is copy-initialized from the clause; in the brace-elided case, the clauses appertaining to its subobjects are collected into a braced list and the element is copy-initialized from that list. Note 4 points out that if the clause is itself a braced list, the element is list-initialized, which applies this subclause recursively when the element is an aggregate.

Aggregate initialization only distributes clauses; how each element is initialized from its clauses is still decided by the element's type:

```cpp run ok
#include <cassert>
struct base1 { int b1, b2 = 42; };
struct base2 { base2() { b3 = 42; } int b3; };
struct derived : base1, base2 { int d; };

int main() {
  derived d1{{1, 2}, {}, 4};
  derived d2{{}, {}, 4};
  assert(d1.b1 == 1 && d1.b2 == 2 && d1.b3 == 42 && d1.d == 4);
  assert(d2.b1 == 0 && d2.b2 == 42 && d2.b3 == 42 && d2.d == 4);
}
```

`base2` has a user-provided constructor and is not an aggregate, so the `{}` given to it is value-initialization per item 5 of [[dcl.init.list#3]], i.e. a call to `base2()`. `base1` is an aggregate; `{}` initializes `b1` from `{}` to 0, and `b2` uses its default member initializer.

Elements are copy-initialized ([[dcl.init#13]]), so `explicit` constructors can't be used here:

```cpp
struct E { explicit E(int); };
struct P { E e; };
P p1{E{1}};   // OK
P p2{1};      // error: e is copy-initialized from 1, and the explicit constructor is not a candidate
```

!!! lawyer "Where the narrowing check for ordinary clauses is written"
    `int a[] = {1, 2.0};` is ill-formed; this is a standard example in Example 3 of [[dcl.init.list#3]], and all implementations reject it. But in the current wording, an explicit ban on narrowing appears only in ¶5.2.1 (the `= expr` form of a designated initializer); ¶5.3 has no corresponding sentence. The C++23 wording had a general rule; after ¶4–¶5 were rewritten in terms of the appertainment model, it survived only in the designated branch.

## Designated initializers (¶3–¶5)

```cpp run ok
struct In { int i, j; };
struct O { In in; int k; };
O o1{.in = {1, 2}, .k = 3};   // OK
O o2{.k = 3};                 // OK: in is initialized from {}
int main() { return o2.in.i; }
```

C++20 **designated initializers** ([[P0329R4]]) specify members by name. They come from C99, but C++ took only a subset. All the restrictions follow from one model: members are initialized in declaration order, and each member exactly once.

| Form | C99 | C++ | Reason |
|---|---|---|---|
| `{.y = 2, .x = 1}` out of order | Allowed | Ill-formed (item 1 of [[dcl.init.list#3]]) | Initialization side effects and destruction order must match declaration order |
| `{.in.i = 1}` nested designator | Allowed | Ill-formed; the grammar has only `. identifier` | Can be written `{.in = {.i = 1}}` |
| `{[3] = 1}` array designator | Allowed | Ill-formed | Conflicts with lambda syntax |
| `{.x = 1, .x = 2}` repeated | The later overrides | Ill-formed ([[dcl.init#20]]) | Each member is initialized only once |
| `{.x = 1.5}` with `x` an `int` | Truncated | Ill-formed (¶5.2.1) | Narrowing |
| `{.x{1}}` | Not allowed | Allowed | Direct-initialization |

Clang 23 accepts out-of-order designators, nested designators, and mixing designated with ordinary clauses as C99 extensions, giving only warnings (`-Wreorder-init-list`, `-Wc99-designator`), and reports errors only with `-pedantic-errors`. Portable code shouldn't rely on them.

### Which element is designated (¶3, ¶4.1)

¶4.1 A designated list can only initialize a class, not an array. Member lookup ([[class.member.lookup]]) of each designator `.id` in class `C` must find exactly one non-static data member, in exactly one subobject, whose type is an **aggregate base** ([[g:aggregate-base|aggregate base]]) of `C`: `C` itself or, recursively, a direct base class of an aggregate base.

A designated member isn't necessarily an element of `C` itself. ¶3 defines the **associated element** of a member M: M itself if M is an element, otherwise the element containing M. ¶4.1 counts the associated element of each designated member as an explicitly initialized element.

This wording allows designating members of base classes, and also initializing a base with ordinary clauses first and then members with designated clauses. It comes from [[P2287R5]] and is new wording after C++23. In C++20/23, a designator could only name a direct member of the class itself, and a list couldn't mix the two kinds of clause.

```cpp
struct A { int a1, a2; };
struct B : A { int b; };
struct C : A { int a1; };

A v0 = A{1, .a2 = 2};             // error: ordinary clauses can only appertain to bases, and A has none
B v1 = B{.a1 = 1, .b = 2};        // the explicitly initialized elements are A and B::b
B v3 = B{A{1, 2}, .b = 3};        // same as above
B v4 = B{A{}, .a2 = 1, .b = 3};   // error: A is initialized in two ways
C v5 = C{.a1 = 4};                // C::a1 hides A::a1; the explicitly initialized element is C::a1
```

The last sentence of ¶4 says that if an element is explicitly initialized through both an ordinary clause and a designated clause, the program is ill-formed; this is the error in `v4`. As of writing, Clang 23 doesn't yet implement designating base class members and reports field designator 'a1' does not refer to any field for `v1`, so this code is analyzed from the standard text only.

### How designated elements are initialized (¶5.1–¶5.2)

- ¶5.2.1 If the element is a direct non-static data member, it is initialized from the *brace-or-equal-initializer* in the corresponding clause. Note 3 points out that the form determines the kind: `.m = e` is copy-initialization, `.m{e}` is direct-list-initialization. The `= e` form is ill-formed if a narrowing conversion is required, even though ordinary copy-initialization allows narrowing.
- ¶5.2.2 If the element is a base class subobject B, all designated clauses whose associated element is B are collected, in their original order, into a designated list, and B is copy-initialized from it. Multiple levels of bases pass things down level by level this way.
- ¶5.1 If the element is an anonymous union, it is initialized with `{ D }`, where `D` is the designated clause naming a member of the union; there can be only one such clause.

```cpp run ok
struct C {
  union { int a; const char* p; };
  int x;
} c = { .a = 1, .x = 3 };     // c.a == 1, c.x == 3
int main() { return c.a + c.x == 4 ? 0 : 1; }
```

The two forms in ¶5.2.1 behave differently with an `explicit` constructor:

<div class="compare" markdown="1">

```cpp ok
struct E { explicit E(int); };
struct P { E e; };
P p1{.e{1}};   // direct-list-initialization
```

```cpp error
struct E { explicit E(int); };
struct P { E e; };
P p2{.e = 1};  // copy-initialization
```

</div>

## Elements not mentioned (¶6–¶7)

```cpp run ok
#include <cassert>
struct S { int a; const char* b; int c; int d = b[a]; };
int main() {
  S ss = { 1, "asdf" };   // c is initialized from {} to 0; d uses its default member initializer, b[a]
  assert(ss.c == 0 && ss.d == 's');
}
```

¶6 In a non-union aggregate, each element that is not explicitly initialized is initialized as follows:

- ¶6.1 if it has a default member initializer ([[class.mem]]), from that;
- ¶6.2 otherwise, if it is not a reference, it is copy-initialized from an empty list, equivalent to `T e = {};`;
- ¶6.3 otherwise, i.e. a reference without a default member initializer, the program is ill-formed.

The example in ¶7 shows that a default member initializer can use earlier elements, as with `d = b[a]` above. For scalars, `int x = {};` is 0, so in `int arr[5] = {1};` the remaining elements are 0. The `= {0}` familiar to C programmers can be written simply as `= {}` in C++.

¶6.2 says copy-initialized from `{}`, not value-initialized. The difference is `explicit` default constructors: copy-list-initialization that selects an explicit constructor is ill-formed. This way, omitting an element has exactly the same effect as writing `{}` for it.

```cpp
struct E { explicit E() = default; };
struct A { int i; E e; };
A a1{1, E{}};   // OK
A a2{1};        // error: e is copy-list-initialized from {}, selecting an explicit constructor
```

¶6.4–¶6.5 For a union: if the initializer list is empty and some variant member has a default member initializer, that member is initialized from it; otherwise the first member is copy-initialized from an empty list.

## Arrays: unknown bound and multidimensional (¶11, ¶14, ¶16)

¶11 When an array of unknown bound is initialized with a braced list, the array's length is the number of explicitly initialized elements:

```cpp run ok
int x[] = { 1, 3, 5 };                   // int[3]
struct X { int i, j, k; };
X a[] = { 1, 2, 3, 4, 5, 6 };            // X[2], relying on brace elision
X b[2] = { { 1, 2, 3 }, { 4, 5, 6 } };   // same values as a
static_assert(sizeof x == 3 * sizeof(int) && sizeof a == 2 * sizeof(X));
int main() {}
```

An array of unknown bound can't be initialized with `{}`; a footnote explains that C++ has no zero-length arrays. Clang and GCC accept `int z[] = {};` as an extension and give a `-Wzero-length-array` warning under `-pedantic`.

Note 6 points out that a default member initializer can't determine the length of a member array: a constructor's *mem-initializer* causes the default member initializer to be ignored, and then the length couldn't be determined. So `struct S { int y[] = { 0 }; };` is ill-formed.

¶14 Multidimensional arrays are initialized in row-major order, with the rightmost subscript varying fastest ([[dcl.array]]). The example in ¶16 shows how brace elision works for multidimensional arrays:

```cpp
int x[2][2] = { 3, 1, 4, 2 };                   // x[0][0]=3, x[0][1]=1, x[1][0]=4, x[1][1]=2
float y[4][3] = { { 1 }, { 2 }, { 3 }, { 4 } }; // only the first of each row is initialized, the rest are 0
float z[4][3] = { 1, 3, 5, 2, 4, 6, 3, 5, 7 };  // same as { {1,3,5}, {2,4,6}, {3,5,7} }
```

The initializer of `z` starts with `{`, but the initializer for `z[0]`, `1`, doesn't, so `z[0]` takes 3 clauses in a row, likewise `z[1]` and `z[2]`, and `z[3]` is initialized from `{}`.

## Unions (¶21–¶22)

¶21 When a union is initialized with a list, there can be at most one explicitly initialized element:

```cpp
union u { int a; const char* b; };
u a = { 1 };                     // OK: initializes the first member
u b = a;                         // OK: copy
u c = 1;                         // error: a union can't be initialized from a single int
u d = { 0, "asdf" };             // error: two explicitly initialized elements
u e = { "asdf" };                // error: an ordinary clause can only go to the first member a
u f = { .b = "asdf" };           // OK: a designated initializer can choose another member
u g = { .a = 1, .b = "asdf" };   // error
```

Before C++20, a list could only initialize the first member of a union; the form of `f` is one of the most practical uses of designated initializers. The note in ¶22 reminds us that when a union is a member of another aggregate, its braces can also be elided.

## Other rules (¶8–¶10, ¶13)

¶8 Elements are initialized in element order, with all value computations and side effects of one element sequenced before the next. Parenthesized aggregate initialization does the same (item 6.2.2 of [[dcl.init#15]]).

¶9 A class aggregate can also be initialized with a single expression without braces, e.g. `S s = other;`; this follows the ordinary rules of [[dcl.init]] and calls the copy constructor.

¶10 Aggregate initialization **potentially invokes** ([[class.dtor]]) the destructor of each element of class type, except anonymous unions. Note 5 explains why: if an exception is thrown while initializing element k, the elements already constructed must be destroyed ([[except.ctor]]). So if an element's destructor is deleted or inaccessible, aggregate initialization is ill-formed, whether or not an exception would actually be thrown:

```cpp error
struct PD { ~PD() = delete; };
struct W { PD p; };
W* w = new W{};   // error: aggregate initialization potentially invokes the deleted PD::~PD
```

¶13 If a default member initializer has a potentially evaluated subexpression that is an aggregate initialization which would use that default member initializer itself, the program is ill-formed; otherwise it would recurse infinitely:

```cpp
struct A;
extern A a;
struct A {
  const A& a1 { A{a, a} };   // OK: both elements given explicitly, no default member initializer used
  const A& a2 { A{} };       // error: A{} would use a2's own default member initializer
};
A a{a, a};                   // OK
struct B { int n = B{}.n; }; // error
```

Clang 23 rejects `a2` and `n`, but the reason it gives is that the default member initializer is needed before the class definition is complete, a different check that fires earlier.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The note in ¶19: an element of an aggregate can be a class with user-declared constructors; initialization of such elements is covered in [[class.expl.init]].

The note in ¶20: whether initialization of an aggregate with static storage duration is static or dynamic is covered in [[basic.start.static]], [[basic.start.dynamic]] and [[stmt.dcl]]. When all elements are constant-initialized, the whole aggregate is constant-initialized and goes straight into the data section with no run-time code.

</details>

## Implementation notes

!!! impl
    - In code generation, aggregate initialization is just a write per element; constant-initialized static objects are written directly into the data section.
    - `std::is_aggregate` (C++17) detects aggregates; generic code used to rely on it to choose between `T{args...}` and `T(args...)`. Since C++20 added parenthesized aggregate initialization ([[dcl.init#15]], [[P0960R3]]), `std::make_unique` and `emplace_back` work with aggregates directly, and this distinction is largely no longer needed.
    - Before C++26 reflection, some libraries (such as Boost.PFR) detected the number of members of an aggregate by whether `T{any, any, ...}` is well-formed.

## History

!!! history
    The definition of aggregate has changed in almost every version:

    | Standard | Constructors | Default member initializers | Base classes |
    |---|---|---|---|
    | C++98/03 | No user-declared ones | (no such feature) | Not allowed |
    | C++11 | No user-provided ones; `= default` and `= delete` don't count | Not an aggregate if present | Not allowed |
    | C++14 | Same as C++11 | Allowed ([[N3653]]) | Not allowed |
    | C++17 | No user-provided, explicit or inherited ones | Allowed | Public non-virtual bases ([[P0017R1]]) |
    | C++20 | No user-declared or inherited ones ([[P1008R1]]) | Allowed | Public non-virtual bases |

    C++11's switch to user-provided was meant to keep classes with `= default` as aggregates, but it left a loophole: `struct ND { ND() = delete; int x; }; ND a{};` was valid in C++11–17, with aggregate initialization bypassing the deleted constructor, and the same went for a private `= default` constructor. C++20 switched back to user-declared and closed the loophole, but `struct S { S() = default; int i; }; S s{1};` has been ill-formed ever since.

    Other changes: since C++11 list-initialization has brought aggregate initialization into a unified framework, and the narrowing check applies along with it; C++14 allowed brace elision in `T x{…}` through [[CWG1270]], so `std::array<int, 3> a{1, 2, 3};` became valid (C++11 only allowed elision in the `= {…}` form); C++20 added designated initializers ([[P0329R4]]), parenthesized aggregate initialization ([[P0960R3]]), and class template argument deduction for aggregates.

## Common misconceptions

!!! pitfall "Adding `S() = default;` just documents that there's a default constructor"
    Since C++20 it makes `S` no longer an aggregate, and every `S s{1, 2};` fails to compile.

!!! pitfall "Initializing an aggregate with parentheses is the same as with braces"
    With `struct R { const int& r; };`, `R a{42};` extends the temporary's lifetime, while `R b(42);` doesn't, and `b.r` dangles immediately ([[class.temporary#6]]). The two forms also differ in narrowing, brace elision and designators; see Note 7 in [[dcl.init#15]].

## Questions

!!! question "Question 1"
    Is `struct X { int a; int b; X() = default; };` an aggregate in C++17 and in C++20? Is `X x{1, 2};` well-formed?

<details markdown="1">
<summary>Answer</summary>

C++17: `X() = default` is explicitly defaulted on its first declaration, so it is neither user-provided nor explicit, `X` is an aggregate, and `X x{1, 2};` is well-formed aggregate initialization.

C++20: `X() = default` is a user-declared constructor, so `X` is not an aggregate. `{1, 2}` goes to the constructor overload resolution of item 7 of [[dcl.init.list#3]]; the only candidates are the default, copy and move constructors, none of which takes two `int`s, so it is ill-formed.
</details>

!!! question "Question 2"
    In `struct A { int i; operator int(); }; struct B { A a; int z; }; A a; B b{a};`, which element does the clause `a` appertain to? What changes if `operator int()` is removed?

<details markdown="1">
<summary>Answer</summary>

The first element of `B`, `b.a`, is an aggregate. The clause `a` doesn't start with `{` but can be implicitly converted to `A` (an identity conversion), satisfying ¶15.3, so it appertains to `b.a`; `b.a` is copy-initialized from `a`, and `b.z` is initialized from `{}` to 0. `operator int` plays no part, and removing it changes nothing.

It only matters when a clause can't convert to the subaggregate type, as in `B b{4, a};`: `4` descends into `b.a` to initialize `b.a.i`, and then `a` appertains to `b.z`, converted via `operator int()`.
</details>
