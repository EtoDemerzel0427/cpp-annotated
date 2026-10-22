---
title: Initializing references
summary: "When a reference is initialized, whether it binds to the initializer expression itself, to the result of a conversion function, or to a newly created temporary; which bindings are ill-formed; and how the standard has gradually turned bindings that must dangle into compile errors."
updated: 2026-10-19
---

!!! tldr
    - Once initialized, a reference refers to one object or function for good; assigning to the reference assigns to that object. Argument passing and `return` are initialization too and follow the same rules.
    - When the types are the same, differ only by added cv-qualification, or are derived-to-base, the reference binds directly to the original object; when the types don't match, `const T&` and `T&&` can bind to a temporary created by conversion, but a non-const lvalue reference can't.
    - An rvalue reference can never bind to an lvalue of a reference-related type, but `double&& r = i;` (with `i` an `int`) is valid: it binds to a newly created temporary `double`.
    - A reference bound to a temporary extends its lifetime, but the extension doesn't pass through function calls; `return` of a reference bound to a temporary is a compile error in C++26.

## What it binds to

```cpp run ok
#include <cstdio>
int main() {
  int i = 1;
  int& r = i;            // r refers to i
  const long& rl = i;    // rl refers to a newly created temporary long
  i = 5;
  std::printf("%d %ld\n", r, rl);   // 5 1
}
```

A reference is not an object; initializing a reference means deciding which object or function it **binds** to. `r` binds to `i` itself; `rl`'s type differs from `i`'s, so the compiler first converts `i` to a temporary `long` and `rl` binds to that temporary, after which modifying `i` has nothing to do with it.

This subclause answers three questions: whether it can bind, whether it binds to the original object or to a temporary, and how long the temporary lives. When the destination type is a reference and the initializer is not a braced list, [[dcl.init#15.2]] hands initialization over to here; the braced case is in [[dcl.init.list]], and mostly comes back here in the end.

Reading this subclause requires knowing value categories ([[basic.lval]], see [[topics/value-categories]]): an lvalue designates an existing object, a prvalue is just a value, and an xvalue is an object whose resources are about to be taken. Lvalues and xvalues together are glvalues; xvalues and prvalues together are rvalues. A reference can only bind to a glvalue; if the initializer is a prvalue, the [[g:temporary-materialization-conversion|temporary materialization conversion]] ([[conv.rval]]) first creates a temporary object and yields an xvalue designating it.

## References must be initialized and can't be reseated (¶1–¶3)

¶1 A variable declared as `T&` or `T&&` must be initialized. Example 1 in the standard shows binding to a variable, a function and an array:

```cpp run ok
int g(int) noexcept { return 0; }
int main() {
  int i;
  int& r = i;            // r refers to i
  r = 1;                 // the value of i becomes 1
  int* p = &r;           // p points to i
  int& rr = r;           // rr also refers to i: there are no references to references
  int (&rg)(int) = g;    // binds to a function
  rg(i);                 // calls g
  int a[3];
  int (&ra)[3] = a;      // binds to an array
  ra[1] = i;             // modifies a[1]
  (void)p; (void)rr;
}
```

¶2 After a reference has been initialized, it can't be changed to refer to another object; assigning to a reference assigns to the object it refers to ([[expr.assign]]). Argument passing ([[expr.call]]) and function return ([[stmt.return]]) are initialization, so `void h(int&); h(1);` fails for the same reason as `int& r = 1;`.

¶3 There are only four places where a reference's initializer can be omitted:

| Place | Example | Who initializes it |
|---|---|---|
| Parameter declaration | `void f(int& r);` | The argument of each call |
| Function return type | `int& g();` | Each `return` executed |
| Member in a class definition | `struct S { int& r; };` | A constructor or aggregate initialization |
| Explicit `extern` | `extern int& r2;` | A definition elsewhere |

<div class="compare" markdown="1">

```cpp ok
extern int& r2;   // non-defining declaration
```

```cpp error
int& r1;          // error: missing initializer
```

</div>

## Reference-related and reference-compatible (¶4)

```cpp
struct Base {}; struct Derived : Base {};
int i;          const int ci = 0;   Derived d;
const int& a = i;    // OK: just adds const
int& b = ci;         // error: would drop const
Base& c = d;         // OK: derived to base
```

Whether direct binding is possible depends on two relations between two types. ¶4 lets the reference's type be *cv1* `T1` and the initializer's type be *cv2* `T2`:

- If `T1` is [[g:similar-types|similar]] to `T2` (the same after removing cv-qualifiers at every level, [[conv.qual]]), or `T1` is a base class of `T2`, *cv1* `T1` is **reference-related** to *cv2* `T2`.
- If "pointer to *cv2* `T2`" can be converted to "pointer to *cv1* `T1`" via a standard conversion sequence, *cv1* `T1` is **reference-compatible** with *cv2* `T2`.

Reference-related asks whether the two are the same kind of thing; reference-compatible asks whether a reference to `T1` can point directly at this `T2` object without trouble. The latter is defined by borrowing pointer conversions: derived-to-base ([[conv.ptr]]), adding cv-qualification ([[conv.qual]]), and dropping `noexcept` from a function type ([[conv.fctptr]]) are all safe pointer conversions, while dropping `const` and base-to-derived are not standard conversions.

| *cv1* `T1` (reference) | *cv2* `T2` (initializer) | Reference-related | Reference-compatible |
|---|---|---|---|
| `const int` | `int` | Yes | Yes: `int*` → `const int*` |
| `int` | `const int` | Yes | No: would drop `const` |
| `Base` | `Derived` | Yes | Yes: derived to base |
| `Derived` | `Base` | No | No |
| `const int* const` | `int*` | Yes (similar) | Yes: `int**` → `const int* const*` |
| `const int*` | `int*` | Yes (similar) | No: `int**` → `const int**` is not a valid qualification conversion |
| `long` | `int` | No | No |

The last sentence of ¶4 says: if binding is allowed by reference-compatibility but the corresponding pointer conversion is itself ill-formed (the base is ambiguous or inaccessible), the program is ill-formed. It doesn't fall back to creating a temporary.

```cpp error
struct B {};
struct D1 : B {}; struct D2 : B {};
struct MD : D1, D2 {} md;
B& rb = md;        // error: B is an ambiguous base

struct PD : private B {} pd;
B& rb2 = pd;       // error: B is an inaccessible base
```

## The binding algorithm (¶5)

¶5 When a reference to *cv1* `T1` is initialized by an expression of type *cv2* `T2`, four branches are checked in order, and the first that applies determines the result:

1. **Lvalue reference binds to an lvalue** (¶5.1): the initializer is a reference-compatible lvalue, or can be converted by a conversion function to a reference-compatible lvalue. Bind directly to it.
2. **Non-const lvalue references stop here** (¶5.2): if the previous branch doesn't apply and the reference is a non-const or `volatile`-qualified lvalue reference, the program is ill-formed.
3. **Binding to an rvalue** (¶5.3): the initializer is a reference-compatible rvalue (or function lvalue), or can be converted by a conversion function to such a result. A prvalue is materialized first, then bound directly.
4. **Creating a temporary** (¶5.4): `T1` must not be reference-related to `T2`; the initializer is converted to `T1` and the reference binds to the resulting temporary.

The following table gives the result by kind of reference and initializer:

| | Lvalue `i` of the same type | Rvalue `int()` of the same type | `long` lvalue | Class convertible to `int&` | Class convertible to `int` |
|---|---|---|---|---|---|
| `int&` | Binds directly (¶5.1.1) | Ill-formed (¶5.2) | Ill-formed (¶5.2) | Binds directly (¶5.1.2) | Ill-formed (¶5.2) |
| `const int&` | Binds directly (¶5.1.1) | Materialized, then binds directly (¶5.3.1) | Temporary (¶5.4.2) | Binds directly (¶5.1.2) | Materialized, then binds directly (¶5.3.2) |
| `int&&` | Ill-formed (¶5.4) | Materialized, then binds directly (¶5.3.1) | Temporary (¶5.4.2) | Ill-formed (¶5.4) | Materialized, then binds directly (¶5.3.2) |

### Lvalue references bind directly to lvalues (¶5.1)

```cpp run ok
struct A { };
struct B : A { operator int&(); } b;
B::operator int&() { static int n; return n; }
double d = 2.0;
double& rd = d;          // rd refers to d
const double& rcd = d;   // rcd refers to d: adding const is reference-compatible
A& ra = b;               // ¶5.1.1: ra refers to the A subobject of b
const A& rca = b;        // same as above
int& ir = B();           // ¶5.1.2: ir refers to the result of operator int&
int main() {}
```

¶5.1.1 is the most common case: the reference is an lvalue reference, the initializer is an lvalue (but not a bit-field), and they are reference-compatible. The reference binds to that lvalue, or to the appropriate base class subobject of it.

¶5.1.2 handles initializers of class type: `T1` is not reference-related to `T2`, and `T2` has a conversion function returning an lvalue reference that yields a reference-compatible lvalue. Candidate conversion functions are enumerated per [[over.match.ref]], and the best is chosen by overload resolution. In `int& ir = B();`, `B()` itself is an rvalue, but ¶5.1.2 only requires the result of the conversion to be an lvalue.

¶5.1.2 requires `T1` not to be reference-related to `T2` so that a derived-to-base binding like `A& ra = b;` is always decided by ¶5.1.1 and can't be hijacked by a user-defined `operator A&()`.

Note 2 points out that these two kinds of direct binding don't apply the lvalue-to-rvalue, array-to-pointer or function-to-pointer conversions: the reference binds to the object itself, not to its value.

### Non-const lvalue references don't accept temporaries (¶5.2)

<div class="compare" markdown="1">

```cpp ok
int i = 2;
const double& r1 = 2.0;
const double& r2 = i;
```

```cpp error
int i = 2;
double& r1 = 2.0;  // error
double& r2 = i;    // error
const volatile int& r3 = 1;
                   // error
```

</div>

¶5.2 If ¶5.1 doesn't apply and the reference is a non-const lvalue reference, or a `volatile`-qualified lvalue reference, the program is ill-formed.

What this rule prevents is silently modifying a temporary. If `double& r2 = i;` could bind to a temporary `double`, `r2 = 3.14;` would modify the temporary and `i` wouldn't change at all. Early versions of C++ did allow such binding; something like `void inc(long& x) { ++x; }` called with an `int` argument incremented only the temporary, and errors of this kind were very hard to notice, so the binding was forbidden.

A `const` reference can't be used to modify the object, so binding it to a temporary doesn't have this problem. `volatile` references are still excluded, because `volatile` requires every access to land on that real object, and substituting a compiler-created temporary defeats its purpose.

### Binding to an rvalue (¶5.3)

```cpp ok
struct A { };
struct B : A { } b;
extern B f();
const A& rca2 = f();     // binds to the A subobject of the materialized B prvalue
A&& rra = f();           // same as above
struct X {
  operator B();
  operator int&();
} x;
const A& r = x;          // ¶5.3.2: binds to the A subobject of the result of operator B()
int i2 = 42;
int&& rri = static_cast<int&&>(i2);  // xvalue: binds directly to i2
B&& rrb = x;             // ¶5.3.2: binds directly to the result of operator B()
```

¶5.3 By this point, the reference is either a const lvalue reference or an rvalue reference. If

- ¶5.3.1 the initializer is an rvalue (but not a bit-field) or a function lvalue, and is reference-compatible; or
- ¶5.3.2 the initializer has class type, `T1` is not reference-related to `T2`, and it can be converted by a conversion function ([[over.match.ref]]) to a reference-compatible rvalue or function lvalue,

then the initializer in the first case, or the result of the conversion in the second, is called the **converted initializer**. If it is a prvalue, let its type be `T4`; the temporary materialization conversion is applied, with the prvalue's type considered to be *cv1* `T4`. The reference binds to the resulting glvalue, or to the appropriate base class subobject of it.

Considering it *cv1* `T4` means the temporary takes on the reference's cv-qualification. The temporary materialized by `const int& x = 42;` has type `const int`, and modifying it through `const_cast` modifies a const object:

```cpp error
constexpr int f() {
  const int& x = 42;
  const_cast<int&>(x) = 1;   // UB: modifies a const object
  return x;
}
constexpr int z = f();       // error: UB during constant evaluation, not a constant expression
```

The same rule lets an array be materialized as a whole with a more const type, without converting element by element:

```cpp ok
typedef int *AP[3];                 // array of 3 int*
typedef const int *const ACPC[3];   // array of 3 const int* const
ACPC&& r = AP{};   // AP is reference-compatible with ACPC: the AP prvalue is materialized as ACPC
```

Function lvalues also fall under ¶5.3, so `void (&&rf)() = g;` is valid. Functions have no resources to move from, and the lvalue/rvalue distinction is meaningless for them.

### Creating a temporary (¶5.4)

```cpp ok
#include <string>
const double& rcd2 = 2;        // temporary const double with value 2.0
double&& rrd = 2;              // temporary double with value 2.0
int i3 = 2;
double&& rrd3 = i3;            // OK: binds to a temporary double converted from i3
const std::string& s = "abc";  // string(const char*) constructs a temporary
```

¶5.4 When none of the first three branches applies, the standard first requires `T1` **not to be reference-related** to `T2`, and only then allows a conversion:

- ¶5.4.1 If `T1` or `T2` is a class type: the conversion is chosen by the rules for copy-initialization of an object of type *cv1* `T1` by user-defined conversion ([[dcl.init#15.6.3]], [[over.match.copy]], [[over.match.conv]]); if the corresponding non-reference copy-initialization would be ill-formed, so is this. The result E of the conversion function call is then used to direct-initialize the reference in the form `(E)`, this time without considering user-defined conversions.
- ¶5.4.2 Otherwise: the initializer is implicitly converted to a prvalue of type `T1`, materialized with type *cv1* `T1`, and the reference binds to the result.

`double&& rrd3 = i3;` looks like an rvalue reference binding to an lvalue, but it actually binds to the converted temporary `double`, and modifying `rrd3` doesn't affect `i3`.

The not-reference-related precondition excludes two kinds of binding:

1. An rvalue reference binding to a reference-related lvalue, such as `double d2; double&& r = d2;`. If this were allowed, any lvalue could be moved from as an rvalue without `std::move`.
2. Dropping cv-qualification, such as `const volatile int cvi = 1; const int& r2 = cvi;`. The two are reference-related but not compatible (the `volatile` would be lost), and it can't fall back to making a copy.

Example 6 in the standard lists the various errors of ¶5.4:

```cpp error
struct Banana { };
struct Enigma { operator const Banana(); };
struct Alaska { operator Banana&(); };
void enigmatic() {
  typedef const Banana ConstBanana;
  Banana&& banana1 = ConstBanana(); // error: reference-related, would drop const
  Banana&& banana2 = Enigma();      // error: see below
  Banana&& banana3 = Alaska();      // error: the conversion result is a Banana lvalue
}
const volatile int cvi = 1;
const int& r2 = cvi;                // error: drops volatile
struct A { operator volatile int&(); } a;
const int& r3 = a;                  // error: the conversion result would drop volatile
double d2 = 1.0;
double&& rrd2 = d2;                 // error: lvalue of a reference-related type
struct X { operator int&(); };
int&& rri2 = X();                   // error: the conversion result is an lvalue of a reference-related type
```

`banana2` has to go through the whole procedure. The result of `operator const Banana()`, `const Banana`, is not reference-compatible with `Banana` (the const would be lost), so ¶5.3.2 doesn't apply. At ¶5.4, `Banana` is not reference-related to `Enigma`, so ¶5.4.1 applies: the result E of the conversion function is a `const Banana` prvalue, which then direct-initializes the `Banana&&` as `(E)`; now `Banana` is reference-related to `const Banana`, which ¶5.4 forbids.

## Direct binding

The end of ¶5 says: in all cases except ¶5.4.2 (implicitly converting the initializer to the referenced type), the reference is said to **bind directly** ([[g:bind-directly|bind directly]]) to the initializer expression. The final direct-initialization `(E)` in ¶5.4.1 comes back to ¶5.1 or ¶5.3, so it also counts as direct binding.

This concept is mainly used in overload resolution. [[over.ics.ref]] says that when a reference parameter binds directly to an argument, the implicit conversion sequence is the identity conversion (or a derived-to-base conversion); when it doesn't bind directly, the conversion sequence is computed as a conversion to the referenced type. Rules in [[over.ics.rank]], such as an rvalue reference binding to an rvalue being better than an lvalue reference, also build on it.

Whether binding is direct has nothing to do with lifetime extension: as long as the reference ultimately binds to a materialized temporary, the lifetime extension of [[class.temporary#6]] applies.

## Bit-fields

```cpp error
struct S { int bf : 3; } s;
int& r1 = s.bf;          // error: a non-const reference can't bind to a bit-field
const int& r2 = s.bf;    // OK: binds to a temporary holding the bit-field's value
```

A bit-field doesn't necessarily start on a byte boundary and has no address, so a reference can't bind to it directly: ¶5.1.1 and ¶5.3.1 both exclude bit-fields. Note 3 in [[class.bit]] explains that a `const int&` binds to a temporary holding the bit-field's value.

!!! lawyer "A gap in the wording"
    Read strictly by the text of ¶5, `const int& r2 = s.bf;` satisfies neither ¶5.1.1 (the initializer is a bit-field) nor ¶5.3.1 (the initializer is an lvalue), so it reaches ¶5.4; and ¶5.4 requires `int` not to be reference-related to `int`, which doesn't hold here. Taken literally, the program is ill-formed. But Note 3 in [[class.bit]] says explicitly that it binds to a temporary, and all mainstream compilers accept it. Notes aren't normative; this is a gap between the wording and the design intent.

## How long the temporary lives (¶6)

¶6 is a note pointing to [[class.temporary]]. The main points follow.

When a reference binds to a temporary or a subobject of one, and the glvalue was obtained through materialization, parentheses, array subscripting, `.` member access, `.*`, a cast not involving a user-defined conversion, the conditional operator or the comma operator, the temporary's lifetime is extended to match the reference's ([[class.temporary#6]]).

A reference obtained through a function call doesn't extend the lifetime, including `std::max`, `std::move` and member functions returning `const T&`, because the compiler doesn't track what a function returns internally.

```cpp run ub
#include <string>
#include <cstdio>
const std::string& id(const std::string& s) { return s; }
int main() {
  const std::string& ok = std::string(40, 'a');       // lifetime extended to the end of ok's scope
  const std::string& bad = id(std::string(40, 'b'));  // the temporary is destroyed at the end of this line
  std::printf("%c %c\n", ok[0], bad[0]);              // UB: bad dangles
}
```

Running with `-fsanitize=address` reports `stack-use-after-scope`.

There are also exceptions where no extension happens: a temporary bound to a reference parameter in a function call, a temporary bound to a reference member in parenthesized aggregate initialization, and a temporary bound to a reference in a *new-initializer* all live only until the end of the containing full-expression (items 6.10–6.12 of [[class.temporary#6]]).

## Turning bindings that must dangle into compile errors

Some bindings are certain to dangle. C++ has gradually moved them from run-time UB to compile errors.

### Member initializers

[[class.base.init#8]] says that binding a reference member to a temporary in a *mem-initializer* is ill-formed; [[class.base.init#13]] says the same for default member initializers, with the error raised when a constructor actually uses that default member initializer.

```cpp error
struct A {
  A() : v(42) { }   // error: the temporary would only live until the constructor ends
  const int& v;
};
```

### Library: detecting binding to temporaries {{c++23}}

[[P2255R2]] added the type traits `std::reference_constructs_from_temporary` and `std::reference_converts_from_temporary`, which determine whether initializing a reference (directly or by copy) from an expression of some type would bind the reference to a temporary. This can't be determined with ordinary template metaprogramming and needs compiler built-in support.

The standard library uses them to delete the constructors of `std::pair` and `std::tuple` that would bind reference members to temporaries, and to make `INVOKE<R>` ill-formed when it would return a dangling reference (for example `std::function<const T&()>` wrapping a function that returns `T`):

```cpp error
#include <tuple>
#include <string>
#include <type_traits>
static_assert(std::reference_constructs_from_temporary_v<const int&, long>);
static_assert(!std::reference_constructs_from_temporary_v<const int&, int&>);
std::tuple<const std::string&> t("abc");   // error: the reference element would bind to a temporary string
```

### `return` binding a temporary {{c++26}}

[[P2748R5]] specifies in [[stmt.return#6]]: if a `return` statement binds the returned reference, or a constituent reference ([[intro.object]]) of the returned object, to a temporary, the program is ill-formed.

```cpp error
auto&& f1() {
  return 42;     // error: the returned reference binds to a temporary
}
const double& f2() {
  static int x = 42;
  return x;      // error: int → double creates a temporary
}
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
  return id(42); // well-formed, but the returned reference dangles: it went through a function call
}
```

The author of `f2` thinks it returns the static variable `x`, but the `const double&` actually binds to a temporary `double` converted from `x` (¶5.4.2). In C++23 it is well-formed and returns a dangling reference, and using it is UB; in C++26 it is a compile error.

This rule exempts the fictional function the standard invents for `std::is_convertible` ([[meta.rel]]); otherwise `is_convertible_v<int, const int&>` would become `false`.

!!! impl
    Clang 23 with `-std=c++2c` reports errors for `f1` and `f2` (returning reference to local temporary object); in C++23 mode it only warns. It doesn't yet report an error when a reference member of the returned object binds to a temporary (as in `struct P { const int& r; }; P g() { return P{42}; }`): the constituent-reference part isn't implemented.

## Implementation notes

!!! impl
    - In mainstream ABIs, reference members and reference parameters are represented like pointers; local reference variables are usually optimized away entirely.
    - A lifetime-extended temporary is a hidden object generated by the compiler: for a reference with automatic storage duration, a hidden local variable on the stack; for a reference at namespace scope, a hidden object in static storage, destroyed together with the reference.
    - Clang's `-Wdangling` family, on by default, catches many bindings that dangle immediately, such as `std::string_view sv = std::string("x");`. GCC's `-Wdangling-reference` tries to detect temporaries passed to functions returning references, but has false positives.

## History

!!! history
    - C++98: non-const lvalue references could only bind to lvalues; const references could bind to rvalues. When a class-type rvalue bound to a const reference, the implementation could first copy it into a temporary and bind to that, so the copy constructor had to be accessible even if no copy was made.
    - C++11: rvalue references introduced. Class rvalues must bind directly, with no extra copy allowed. ¶5 has since been rewritten several times to handle the combination of rvalue references and conversion functions.
    - After C++14 (defect report): binding a reference member to a temporary in a *mem-initializer* became ill-formed.
    - C++17: [[P0135R1]] introduced temporary materialization, and ¶5.3 switched to the wording of a converted initializer plus materialization.
    - Around C++20 (defect report): reference-related was redefined in terms of similar types, so `const int* const& r = p;` (with `p` an `int*`) binds directly to `p` instead of creating a temporary.
    - C++23: the type traits of [[P2255R2]], and the standard library's bans on dangling bindings.
    - C++26: [[P2748R5]]: `return` binding a temporary is ill-formed.

## Common misconceptions

!!! pitfall "`const T&` parameters plus a returned reference"
    In `const auto& m = std::max(a, b + 1);`, the temporary for `b + 1` is destroyed at the end of the line, and `m` may dangle. Lifetime extension only applies to the reference that binds directly to the temporary; it doesn't pass through function calls.

!!! pitfall "Seemingly bound to a variable, actually bound to a temporary"
    After `int i = 0; const long& r = i; i = 5;`, `r` is still 0, because `r` binds to a converted temporary `long`. The same happens when `void f(const long&)` receives an `int` argument.

!!! pitfall "Range-for and chained calls"
    In `for (auto& x : make_obj().items())`, in C++20 and earlier only the result of `items()` binds to the hidden reference, and the temporary returned by `make_obj()` is destroyed at the end of the initializer. C++23's [[P2718R0]] makes all temporaries in the *for-range-initializer* live until the end of the loop ([[class.temporary#7]]).

## Questions

!!! question "Question 1"
    What does each line bind to? Which are ill-formed?
    ```cpp
    struct B {}; struct D : B {};
    D make();
    D d;
    B&& r1 = make();
    B&& r2 = d;
    B&& r3 = std::move(d);
    const B& r4 = make();
    B& r5 = make();
    ```

<details markdown="1">
<summary>Answer</summary>

- `r1`: `make()` is a `D` prvalue, and `B` is reference-compatible with `D`, so ¶5.3.1 applies: a `D` temporary is materialized and the reference binds to its `B` subobject, with lifetime extension.
- `r2`: `d` is an lvalue. ¶5.1 only covers lvalue references and ¶5.3.1 requires an rvalue, so neither applies; ¶5.4 requires `B` not to be reference-related to `D`, but `B` is a base of `D`, so it is ill-formed.
- `r3`: `std::move(d)` is an xvalue; ¶5.3.1 applies and the reference binds directly to the `B` subobject of `d`, with no temporary created.
- `r4`: same as `r1`; binds to the `B` subobject of the materialized temporary, with lifetime extension.
- `r5`: a non-const lvalue reference with an rvalue initializer, ill-formed by ¶5.2.
</details>

!!! question "Question 2"
    Why is `double&& r = i;` (with `i` an `int` lvalue) well-formed while `int&& r = i;` is ill-formed? Is this asymmetry reasonable?

<details markdown="1">
<summary>Answer</summary>

`int&& r = i;`: `int` is reference-related to `int`, and `i` is an lvalue. ¶5.3 requires an rvalue and ¶5.4 requires the types not to be reference-related; neither holds, so it is ill-formed.

`double&& r = i;`: `double` is not reference-related to `int`, so ¶5.4.2 applies: `i` is converted to a `double` prvalue and materialized, and `r` binds to this new temporary.

The asymmetry is reasonable. An rvalue reference means the resources of the bound object can be taken. If `int&& r = i;` were valid, it would allow taking `i`'s resources while `i` is still used afterwards; `double&& r = i;` binds to a temporary unrelated to `i` that no one else can use, so taking its resources is safe. What the rule really forbids is binding an rvalue reference to an existing lvalue object.
</details>

!!! question "Question 3"
    What happens with `get` below in C++23 and in C++26?
    ```cpp
    struct Cfg { long timeout; };
    const int& get(const Cfg& c) { return c.timeout; }
    ```

<details markdown="1">
<summary>Answer</summary>

`c.timeout` is a `const long` lvalue, and `int` is not reference-related to `long`, so ¶5.4.2 applies: it is converted to an `int` prvalue and materialized, and the returned reference binds to that temporary. The temporary is destroyed at the end of the `return` statement, and the returned reference dangles.

In C++23 the program is well-formed, but using the return value is UB, and compilers usually warn. In C++26, [[stmt.return#6]] makes it ill-formed, and Clang 23 reports an error with `-std=c++2c`.
</details>
