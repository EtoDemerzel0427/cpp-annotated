---
title: Core constant expressions
summary: "What an expression may not do when evaluated at compile time: read or write run-time objects, call non-constexpr functions, trigger undefined behavior, type-pun, carry allocated memory out of the evaluation, and so on; and how compilers deal with references and objects whose values are unknown."
updated: 2026-10-19
---

!!! tldr
    - Core constant expressions are defined by exclusion: the compiler evaluates the expression according to the rules of the abstract machine, and as long as it performs none of the 36 kinds of operations listed in paragraph 2 along the way, it is a core constant expression.
    - The list only checks operations that are actually executed. A `throw`, `goto` or non-constexpr call in a branch that isn't executed has no effect.
    - Reads and writes are bounded by lifetime: objects created during this evaluation can be read and written freely; objects that existed before can only be read, and only if they are usable in constant expressions. That is why the parameters of a constexpr function are not constant expressions inside its body.
    - Core-language undefined behavior and erroneous behavior are never allowed in constant evaluation, so the compiler can catch them for you at compile time; library undefined behavior is not guaranteed to be caught.
    - References or objects whose values are unknown at compile time (since C++23) can still be passed around, have their addresses taken, and have member functions called on them that don't read members; you just can't read their values or depend on their dynamic types.

## The same function, sometimes constant and sometimes not

```cpp
#include <climits>
constexpr int add(int a, int b) { return a + b; }

constexpr int x = add(1, 2);         // OK
constexpr int y = add(INT_MAX, 1);   // error: signed overflow
int n = 1;
constexpr int z = add(n, 1);         // error: reads the run-time variable n
```

Declaring `add` constexpr only means it can be called at compile time. Whether a particular call can be completed at compile time depends on what that evaluation actually does.

¶2 The standard answers this with a list. If evaluating an expression E according to the rules of the abstract machine ([[intro.execution]]) would evaluate none of the 36 kinds of operations on the list, E is a **core constant expression**.

The definition has three key points:

- It looks only at the operations actually executed, not at what is written in the code. `constexpr int f(bool b) { return b ? 1 : throw 0; }` contains a `throw`, but `f(true)` doesn't execute it, so `f(true)` is a core constant expression.
- The evaluation of E includes every function it calls. The list applies to the whole call tree, not just to the subexpressions of E itself.
- A core constant expression only constrains the evaluation. The result must also satisfy additional conditions (no dangling pointers, no indeterminate values, etc.) to be a **constant expression**; see [[expr.const.const]]. Array bounds, template arguments and the initializers of constexpr variables all require the latter.

## Reads and writes: bounded by lifetime

### Reading (¶2.10)

¶2.10 In the standard, reading the value of an object is called an **lvalue-to-rvalue conversion** ([[g:lvalue-to-rvalue-conversion|lvalue-to-rvalue conversion]], [[conv.lval]]). Only three kinds of reads are allowed in constant evaluation:

1. Reading an object of type `std::nullptr_t` (2.10.1). It has only one possible value, so reading it needs no memory access, and it doesn't matter even if the object is uninitialized.
2. Reading an object [[g:usable-in-constant-expressions|usable in constant expressions]], not through a volatile glvalue (2.10.2). The values of such objects are fixed at compile time; they include constexpr variables, `const` integral or enumeration variables initialized with constants, string literals, template parameter objects, and their non-mutable subobjects. The full definition is in [[expr.const.init#7]].
3. Reading an object of literal type whose lifetime began within the evaluation of E, again not through volatile (2.10.3). That is, local variables, temporaries and `new`-ed objects created by this evaluation itself.

```cpp
const int ci = 5;          // const int, initialized with a constant
static_assert(ci == 5);    // OK: usable in constant expressions

int nc = 5;
static_assert(nc == 5);    // error: nc is not const

const double cd = 1.0;
static_assert(cd == 1.0);  // error: only integral and enumeration types get this special case

const volatile int vi = 1;
static_assert(vi == 1);    // error: volatile

constexpr int local() {
  int x = 1;               // lifetime begins within this evaluation
  x += 2;
  return x;
}
static_assert(local() == 3);   // OK

constexpr bool np() {
  decltype(nullptr) p;     // uninitialized
  return p == nullptr;     // OK: reading nullptr_t doesn't access memory
}
static_assert(np());
```

A `const int` can be used in constant expressions without writing constexpr, but a `const double` cannot; this is a special case left over from C++98, which allowed const integral variables initialized with constants as array bounds. Later standards kept it but never extended it to other types. [[expr.const.init#6]] calls such variables potentially-constant. To make a `double` variable usable in constant expressions, write `constexpr`.

### Modification and destruction (¶2.18–¶2.19)

```cpp
int g = 0;
constexpr int touch() { return ++g; }
constexpr int e1 = touch();      // error: g was not created by this evaluation

constexpr int k = 1;
constexpr int cheat() { return ++const_cast<int&>(k); }
constexpr int e2 = cheat();      // error: likewise (and UB at run time too)
```

¶2.18 Assignment, compound assignment, and increment and decrement can only act on non-volatile objects of literal type created during this evaluation. Modifying an outside object would leave a side effect of compile-time evaluation, and compile-time side effects cannot be carried over to run time.

C++11 constant evaluation didn't allow modification at all. C++14 relaxed it to today's rule, which is what made it possible to write loops and local variables in constexpr functions.

¶2.19 Destruction works the same way: a destructor or pseudo-destructor cannot be invoked in constant evaluation to end the lifetime of an object from outside the evaluation.

### Why parameters are not constant expressions (¶5)

¶5 The standard's example makes the lifetime boundary clear:

```cpp
constexpr int f1(int k) {
  constexpr int x = k;     // error: k's lifetime began outside the initializer of x
  return x;
}
constexpr int f2(int k) {
  int x = k;               // OK: a non-constexpr variable doesn't need a constant initializer
  return x;
}

constexpr int incr(int& n) { return ++n; }
constexpr int g(int k) {
  constexpr int x = incr(k);   // error: modifies k, which was not created by incr(k)
  return x;
}
constexpr int h(int k) {
  int x = incr(k);             // OK
  return x;
}
constexpr int y = h(1);        // OK: y == 2
```

The key is to be clear about which expression E is. `constexpr int x = k;` in `f1` requires a constant expression of its own; there E is `k`, and the parameter `k` was not created during the evaluation of `k`. So this line is invalid regardless of whether `f1` is called at compile time.

`y = h(1)` is different. There E is `h(1)`, the parameter `k` is created by that evaluation, and `incr` may modify it freely.

`static_assert`, array bounds and template arguments are also independent constant expressions, so the following is invalid too:

```cpp error
#include <array>
constexpr int size_of(int n) {
  std::array<int, n> a{};    // error: n is not a constant expression
  return a.size();
}
```

To pass a value into a function as a compile-time constant, use a template parameter.

## Undefined behavior is never allowed

### Core-language UB and erroneous behavior (¶2.8)

!!! std
    an operation that would have undefined or erroneous behavior as specified in Clause [intro] through Clause [cpp];

```cpp
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int a1 = add(INT_MAX, 1);   // error: signed overflow

constexpr int oob() { int a[3]{}; return a[3]; }
constexpr int a2 = oob();             // error: out-of-bounds read

constexpr int a3 = 1 / 0;             // error: division by zero
constexpr int a4 = 1 << 32;           // error: shift count not less than the width

constexpr int dangling() {
  int* p;
  { int x = 1; p = &x; }
  return *p;                          // reads an object whose lifetime has ended
}
constexpr int a5 = dangling();        // error
```

Clang rejects all five initializations above. Footnote 62 lists signed overflow, certain pointer arithmetic, division by zero and certain shifts as examples, but the actual scope is all UB in the core language (Clauses 4 through 15), including dereferencing a null pointer, violating strict aliasing, and so on.

The standard has two reasons for this. First, the value of a constant must be determined: if UB could also produce a value, different compilers would write different values into the program, and a type like `X<INT_MAX + 1>` would have no portable meaning. Second, the compiler is already simulating the abstract machine and knows the type, bounds and lifetime of every object, so checking for these errors is much easier than at run time.

C++26 introduced **erroneous behavior** ([[g:erroneous-behavior|erroneous behavior]], [[P2795R5]]): reading an uninitialized automatic variable changed from UB to erroneous behavior, whose result is a determined erroneous value. Item 2.8 lists erroneous behavior too, so such reads are still not allowed in constant evaluation:

```cpp error
constexpr int uninit() {
  int x;        // C++26: x has an erroneous value
  return x;     // erroneous behavior
}
constexpr int v = uninit();   // error
```

### Unions, indeterminate values, arrays of unknown bound (¶2.11, ¶2.12, ¶2.17)

Several other items list specific cases of UB.

¶2.11 Reading an inactive member of a union is not allowed. Since C++20, the active member can be switched by assignment during constant evaluation ([[P1330R0]]):

```cpp
union U { int i; float f; };
constexpr float pun() { U u{.i = 1}; return u.f; }
constexpr float x = pun();       // error: reads the inactive member f

constexpr int sw() {
  U u{.i = 1};
  u.f = 2.0f;                    // the active member switches to f
  return (int)u.f;
}
static_assert(sw() == 2);        // OK
```

¶2.12 Reading an object with an [[g:indeterminate-value|indeterminate value]] is not allowed. In C++26 most uninitialized automatic variables have erroneous values, handled by item 2.8; indeterminate values still exist, for example in variables marked `[[indeterminate]]` and in freshly allocated, uninitialized dynamic objects.

¶2.17 Pointer arithmetic is not allowed when one side is a pointer to the first element of an array of unknown bound and the other is a non-zero integer. The compiler doesn't know how long the array is and cannot tell whether it goes out of bounds; adding zero is always safe.

```cpp
extern int ea[];                 // unknown bound
constexpr int* p0 = ea + 0;      // OK
constexpr int* p1 = ea + 1;      // error
```

### Floating-point operations (¶2.9)

¶2.9 IEEE 754 says `1.0 / 0.0` yields infinity, but the standard counts operations whose result is not in the range of representable values, or is mathematically undefined, as UB ([[expr.pre#4]]). Item 2.9 draws the line precisely; the following three kinds of arithmetic operations are not allowed:

- all operands are finite, but the result is not (overflow to infinity, `1.0 / 0.0`, `0.0 / 0.0`);
- an operand is a signaling NaN;
- no operand is a NaN, but the result is a NaN.

In other words, existing infinities and quiet NaNs may keep taking part in arithmetic, but new ones cannot be produced during constant evaluation.

```cpp
#include <limits>
using L = std::numeric_limits<double>;
constexpr double d1 = L::infinity() * 2;   // OK: the operand is already infinite
constexpr double d2 = 1.0 / 0.0;           // error
constexpr double d3 = 0.0 / 0.0;           // error
constexpr double d4 = L::max() * 2;        // an error by the standard
```

!!! impl "Clang's deviation"
    Clang 23 rejects `d2` and `d3` (reporting division by zero) but accepts `d4`. A multiplication of finite values overflowing to infinity is not a constant under item 2.9.1; Clang hasn't caught up with this yet.

### Library UB: unspecified (¶4)

¶4 If E would perform an operation specified as UB in the library Clauses (Clause 16 onwards), or would call `va_start`, it is unspecified whether E is a core constant expression.

Requiring every library implementation to check all preconditions during constant evaluation would cost too much. In practice, code like `std::array<int, 3>{}[3]` is usually rejected in constant evaluation, because the library implementation ends up performing an out-of-bounds access at the core-language level. But that is only a by-product of the implementation; the standard guarantees nothing.

### A failed `[[assume]]`: implementation-defined (¶3)

¶3 **Runtime-undefined behavior** ([[defns.undefined.runtime]]) is UB at run time, and whether it makes E non-constant in constant evaluation is implementation-defined. Currently it has only one source: the `expr` in `[[assume(expr)]]` being false ([[dcl.attr.assume]]).

```cpp impl
constexpr int as(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int e = as(-1);   // Clang chooses to reject
```

Diagnosis is not mandated because the assumption expression is normally not evaluated at all. To check it, the compiler would have to evaluate an extra, potentially expensive expression.

## Function calls (¶2.3–¶2.7)

```cpp
constexpr int f();                 // declaration only
constexpr int a = f();             // error: f is not yet defined at this point
constexpr int f() { return 1; }
constexpr int b = f();             // OK

int rt();                          // non-constexpr
constexpr int g(bool x) { return x ? 1 : rt(); }
constexpr int c = g(true);         // OK: rt() is not called
constexpr int d = g(false);        // error: calls a non-constexpr function
```

The following calls are not allowed:

- ¶2.3 Calling a non-constexpr function. Footnote 61 explains that overload resolution proceeds as usual; it does not switch to a different candidate because one isn't constexpr.
- ¶2.4 Calling a constexpr function that is not yet defined at the point of evaluation.
- ¶2.5 Calling an instantiation of a constexpr function that is not [[g:constexpr-suitable]]. Currently the only case is a coroutine: a function template declared constexpr, one of whose instantiations is a coroutine. That instantiation is still valid; it just can't be called in constant evaluation ([[dcl.constexpr#3]]).
- ¶2.6 Calling a virtual function on an object whose dynamic type is unknown; see constexpr-unknown below. When the dynamic type is known, virtual functions can be called since C++20.

In C++20 and earlier, a constexpr function that could never produce a constant (such as `constexpr int g() { return rt(); }`) was IFNDR (ill-formed, no diagnostic required). C++23's [[P2448R2]] removed that rule; such functions are now valid, and every call to one in constant evaluation hits item 2.3. Clang still reports `constexpr function never produces a constant expression` under `-std=c++20`.

¶2.7 An expression that exceeds the implementation limits is not a core constant expression either. The quantities suggested in Annex [[implimits]] include at least 512 levels of recursive constexpr calls and at least 1 048 576 full-expressions per evaluation. With this item, a constant evaluation stuck in an infinite loop has a defined outcome: the expression is not a constant, and the compiler doesn't hang.

!!! impl "Adjusting the limits"
    Clang uses `-fconstexpr-depth=` (default 512) and `-fconstexpr-steps=` (default 1048576); GCC uses `-fconstexpr-depth=`, `-fconstexpr-loop-limit=` and `-fconstexpr-ops-limit=`; MSVC uses `/constexpr:depth` and `/constexpr:steps`.

## Static local variables (¶2.2)

¶2.2 When control flows through the declaration of a block variable with static or thread storage duration, that variable must be usable in constant expressions.

<div class="compare" markdown="1">

```cpp ok
constexpr char test() {
  static const int x = 5;
  static constexpr char c[] =
      "Hello World";
  return *(c + x);
}
static_assert(' ' == test());
```

```cpp error
constexpr int counter() {
  static int k = 0;
  return ++k;
}
// error: control passes through a mutable static
constexpr int c = counter();
```

</div>

At run time, a static local variable is initialized the first time control passes through it, and its value is shared between calls. If constant evaluation could pass through a mutable `static int`, the state seen at compile time and at run time would diverge. On the left, `x` and `c` are both immutable, so there is no such problem.

In C++20 and earlier, static variables could not be defined in a constexpr function body at all. C++23 first allowed them in branches that aren't executed ([[P2242R3]]), then allowed control to pass through `static constexpr` variables ([[P2647R1]]); together these give today's item 2.2.

## Type punning (¶2.15–¶2.16)

¶2.15 {{c++26}} A conversion from `void*` to `T*` requires the pointer to be null or to actually point to an object whose type is [[g:similar-types|similar]] to `T`.

```cpp
constexpr int ok() {
  int x = 42;
  void* p = &x;
  return *static_cast<int*>(p);     // OK: p really points to an int
}
static_assert(ok() == 42);

constexpr int bad() {
  int x = 42;
  void* p = &x;
  return *static_cast<short*>(p);   // it points to an int
}
constexpr int b = bad();            // error
```

In C++23 and earlier, any `static_cast` from `void*` made the expression non-constant, so type-erased containers couldn't be used at compile time. The compiler already knows the real type of every object, and checking a conversion back to the original type is cheap, so [[P2738R1]] allowed this case.

¶2.16 `reinterpret_cast` is never allowed, even when the conversion would be valid at run time:

```cpp error
constexpr int first_byte() {
  int x = 1;
  return *reinterpret_cast<unsigned char*>(&x);   // byte access that is valid at run time
}
constexpr int fb = first_byte();   // error
```

The compiler's constant evaluator maintains a typed object model with no notion of object representation (bytes). To inspect bytes at compile time, use `std::bit_cast` ([[bit.cast]]).

## Dynamic memory: allocations must be freed within the evaluation (¶2.20–¶2.23, ¶6)

```cpp
#include <vector>
constexpr int sum() {
  std::vector<int> v{1, 2, 3};
  v.push_back(4);
  int s = 0;
  for (int x : v) s += x;
  return s;                    // v has released its memory before returning
}
static_assert(sum() == 10);    // OK

constexpr int* leak() { return new int(1); }
constexpr int* p = leak();     // error: the allocation is not freed within the evaluation

constexpr std::vector<int> gv{1, 2, 3};   // error: likewise
```

C++20's [[P0784R7]] allows constant evaluation to use dynamic memory, provided the allocation is transient:

- ¶2.20.1 a *new-expression* may only call a replaceable global allocation function, and the allocated storage must be deallocated within the evaluation of E;
- ¶2.21 a *delete-expression* may only deallocate storage allocated within E;
- ¶2.22–¶2.23 likewise for `std::allocator<T>::allocate` and `deallocate`.

Why can't allocated memory survive into run time? Then memory allocated at compile time would have to become static storage, and run-time code might call `delete` on it, freeing memory that the run-time allocator never allocated. This problem is still unsolved as of C++26, so you still cannot write a `constexpr std::vector` variable.

¶2.20.2 {{c++26}} [[P2747R2]] additionally allowed placement new that doesn't allocate (`::new (p) T(...)`), provided the storage `p` points to was obtained within E and the original object can be transparently replaced by the new one ([[basic.life]]).

```cpp ok
#include <memory>
#include <new>
constexpr int pn() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  ::new (p) int(7);            // C++26: placement new in constant evaluation
  int r = *p;
  std::destroy_at(p);
  al.deallocate(p, 1);
  return r;
}
static_assert(pn() == 7);
```

In C++20 and C++23 the same thing could only be done with `std::construct_at`, which was introduced precisely to work around placement new being unusable in constant evaluation.

¶6 The bodies of the member functions of `std::allocator<T>` are not considered. The library implementation may use non-constant-evaluable techniques internally; the standard only cares about the fact that `allocate` and `deallocate` were called.

## Exceptions (¶2.24–¶2.25, ¶2.31) {{c++26}}

```cpp
constexpr int ex() {
  try { throw 1; }
  catch (int e) { return e; }
}
static_assert(ex() == 1);   // C++26: OK; C++23: error
```

C++26's [[P3068]] allows exceptions to be thrown and caught in constant evaluation, but an exception cannot escape the evaluation:

- ¶2.24 a constructed exception object, together with any copies produced by `std::current_exception` or `std::rethrow_exception`, must be destroyed within E;
- ¶2.25 a `throw;` without an operand may only rethrow an exception constructed within E;
- ¶2.31 if a `dynamic_cast`, `typeid` or *new-expression* would need to throw an exception such as `std::bad_cast`, `std::bad_typeid` or `std::bad_alloc`, but the definition of the exception type is not reachable (for example `<typeinfo>` or `<new>` was not included), it is not allowed.

!!! impl "Implementation status"
    Clang 23 still rejects `ex()` above; it doesn't implement [[P3068]] yet. In C++23 and earlier, evaluating a *throw-expression* makes the expression non-constant; `try` blocks may appear in constexpr functions since C++20, but a `catch` is never reached in constant evaluation.

## Pointer equality comparisons (¶2.28–¶2.29, ¶1)

¶2.28 Comparisons with unspecified results are not allowed. The most common is ordering the addresses of two unrelated objects:

```cpp
int g1, g2;
constexpr bool c1 = &g1 < &g2;     // error: the ordering is unspecified
constexpr bool c2 = &g1 == &g2;    // OK: false
```

¶2.29 String literals, the backing arrays of `std::initializer_list` and the like are **potentially non-unique objects** ([[intro.object#9]]). An implementation may let such objects with identical or overlapping contents share storage, so `"foo" == "foo"` may be true or false at run time.

If two pointer values come from different evaluations ([[basic.compound#4]]), comparing them with `==` is not a core constant expression when either of the following holds:

- the two might point to the same offset within the same potentially non-unique object;
- one of them points to an object whose type has a constexpr-unknown representation (see below).

```cpp
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";              // error: the two literals might share storage
constexpr bool b2 = f() == f();                   // error: likewise
constexpr const char* p = f();
constexpr bool b3 = p == p;                       // OK: true, the same pointer value
constexpr bool b4 = "xfoo" + 1 == "foo\0y";       // error: might be merged into "xfoo\0y"
constexpr bool b5 = "foo" == "bar" + 0;           // OK: false, different contents
constexpr bool b6 = (const char*)"foo" == "oo";   // OK: false, different offsets even if merged
```

In `b4`, `"xfoo" + 1` and `"foo\0y"` share their first four characters, so the two could be placed in the same storage, and the result depends on the implementation. `b5` and `b6` can be shown never to point to the same place, so their results are definitely false.

¶1 The second case uses an auxiliary concept. A type T **has a constexpr-unknown representation** ([[g:constexpr-unknown-representation|constexpr-unknown representation]]) if it is a union, `std::meta::info`, a pointer or pointer-to-member type, a volatile-qualified type, a class with a reference member, or a type with a base class or member that has such a representation. The bytes of these types cannot be determined at compile time: the bit pattern of a pointer depends on the load address, and a null pointer isn't necessarily all zeros; the bytes of a union depend on its active member. The conditions for constant-evaluating `std::bit_cast` ([[bit.cast]]) use this concept too.

```cpp
#include <initializer_list>
constexpr std::initializer_list<int*> il1 = {(int*)nullptr};
constexpr std::initializer_list<unsigned long> il2 = {0};
constexpr bool b7 = il1.begin() == (void*)il2.begin();   // an error by the standard
```

The compiler doesn't know whether the bytes of `nullptr` and `0UL` are the same, so it cannot rule out the two backing arrays being merged. Clang 23 accepts `b7`; it doesn't implement this rule yet.

## References and objects unknown at compile time (¶9)

```cpp ok
#include <cstddef>
template <typename T, std::size_t N>
constexpr std::size_t array_size(T (&)[N]) { return N; }

void use_array(int const (&arr)[2]) {
  constexpr auto n = array_size(arr);   // OK since C++23
  static_assert(n == 2);
}
```

`array_size` doesn't read the array at all; it only uses the template parameter `N`. But in C++20, passing the reference parameter `arr` as an argument requires evaluating `arr`, and a reference must be initialized with a constant to be usable in a constant expression, which a parameter clearly isn't, so this code was invalid. `std::size(arr)` had the same problem.

¶9 [[P2280R4]] fixed this. During constant evaluation, an *id-expression*, *splice-expression* or `*this` that refers to an object or reference from outside the evaluation is treated as referring to a specific instance, which, together with all its subobjects, is within its lifetime throughout the evaluation:

- if the object is not usable in constant expressions, its dynamic type is **constexpr-unknown** ([[g:constexpr-unknown]]);
- if the reference is not usable in constant expressions, it is treated as binding to an unspecified object of the referenced type, whose dynamic type is also constexpr-unknown.

Intuitively, the compiler can do things with a reference of unknown value that don't need its value: take its address, pass it on, call non-virtual functions that don't read members. As soon as it has to read the value, call a virtual function, or perform a `dynamic_cast` or polymorphic `typeid`, it hits the list.

```cpp
#include <typeinfo>
struct Swim {
  constexpr int phelps() { return 28; }
  virtual constexpr int lochte() { return 12; }
  int coughlin = 12;
};

constexpr int how_many(Swim& swam) {
  Swim* p = &swam;
  return (p + 1 - 1)->phelps();
}

void splash(Swim& swam) {
  static_assert(swam.phelps() == 28);       // OK: reads no value of swam
  static_assert((&swam)->phelps() == 28);   // OK
  Swim* pswam = &swam;
  static_assert(pswam->phelps() == 28);     // error: reads the pointer variable pswam
  static_assert(how_many(swam) == 28);      // OK: p is created within the evaluation
  static_assert(Swim().lochte() == 12);     // OK: the dynamic type is known
  static_assert(swam.lochte() == 12);       // error: dynamic type unknown, cannot call a virtual function
  static_assert(swam.coughlin == 12);       // error: reads an object not usable in constant expressions
}

extern Swim dc;
extern Swim& trident;
constexpr auto& sandeno   = typeid(dc);       // OK: can only be typeid(Swim)
constexpr auto& gallagher = typeid(trident);  // error: dynamic type unknown
```

¶2.30 A `dynamic_cast` or polymorphic `typeid` on an object whose dynamic type is unknown is not allowed, and neither is calling a virtual function (item 2.6). `trident` is a reference and might be bound to an object of a class derived from `Swim`, so `typeid(trident)` is invalid. `dc` is a variable declared as `Swim`, whose most derived type can only be `Swim`, so the standard's example rules `typeid(dc)` OK, and Clang accepts it too.

!!! lawyer "The wording and the example disagree"
    Read literally, paragraph 9 says `dc` is not usable in constant expressions, so its dynamic type is constexpr-unknown, and `typeid(dc)` should hit item 2.30. Yet the standard's example rules it valid. The reasonable reading is that the dynamic type of a complete object declared directly by a variable can only be the declared type. The normative text doesn't spell this out.

Clang 23 accepts `use_array` in `-std=c++23` and later, and still rejects it under `-std=c++20`.

### `this` (¶2.1)

¶2.1 `this` may only be evaluated in two situations: inside a constexpr function being evaluated as part of E (2.1.1), or as the left side of a member access `this->m` (including the implicit `m`) (2.1.2). The second case works together with paragraph 9: in a non-constexpr member function, `*this` is an object of unknown dynamic type, and as long as the called member function doesn't read its members, its value isn't needed.

```cpp
struct S {
  static constexpr int cap() { return 4; }
  constexpr int sz() const { return 3; }   // reads no members
  void f() {                               // non-constexpr member function
    static_assert(this->cap() == 4);       // OK by the standard
    static_assert(sz() == 3);              // OK by the standard
  }
};
```

!!! impl "Clang's deviation"
    Clang 23 rejects both `static_assert`s, reporting `static assertion expression is not an integral constant expression`; it doesn't implement item 2.1.2 yet.

## Lambdas, union copies and structured bindings

### Odr-use of enclosing variables in a lambda (¶2.14)

¶2.14 If a lambda refers to `this` or to an automatic variable outside the lambda in a way that is an [[g:odr-use]] (needing the variable itself, not just its value; see [[basic.def.odr]]), the expression is not a core constant expression.

```cpp
void g() {
  const int n = 0;
  [=] {
    constexpr int i = n;       // OK: only uses the value of n, not an odr-use
    constexpr int j = *&n;     // error: taking the address is an odr-use of n
  };
}
```

An odr-use triggers a capture, and a captured `n` is actually a member of the closure object, which exists at run time. `constexpr int i = n;` only reads the value of a variable usable in constant expressions, which is not an odr-use and needs no capture.

Note 1 adds: when the function call operator of a closure is invoked, captured names have already been transformed into accesses to closure members ([[expr.prim.lambda.capture]]) and no longer refer to the enclosing variables, so item 2.14 doesn't constrain them. Creating and calling closures inside a constant evaluation is therefore perfectly fine:

```cpp ok
auto monad = [](auto v) { return [=] { return v; }; };
auto bind  = [](auto m) { return [=](auto fvm) { return fvm(m()); }; };
static_assert(bind(monad(2))(monad)() == monad(2)());
```

!!! impl "Clang's deviation"
    Clang 23 doesn't reject `constexpr int j = *&n;` above (the lambda is never called, and Clang doesn't check this initializer). By the standard it is ill-formed.

### Copying unions (¶2.13, ¶7)

¶7 A trivial copy or move of a union is just a byte copy at run time, but the constant evaluator has no notion of bytes. The standard says it is treated as copying the active member, and the active member is carried over.

```cpp ok
union U { int i; float f; };
constexpr float h() {
  U a{.f = 1.5f};
  U b = a;         // treated as copying the active member f
  return b.f;      // OK
}
static_assert(h() == 1.5f);
```

¶2.13 If the active member is `mutable`, copying amounts to reading a value that can change at run time. So such a copy is not allowed unless the union object was created during this evaluation:

```cpp
union V { mutable int m; int n; };
constexpr V u{.m = 1};
constexpr V v = u;          // error: the active member m is mutable

constexpr int local() { V a{.m = 1}; V b = a; return b.m; }
static_assert(local() == 1);   // OK: a was created by this evaluation
```

### Structured bindings (¶8)

¶8 During constant evaluation, the name of a structured binding is treated according to what it actually refers to ([[dcl.struct.bind]]): if it is bound to an invented reference (the tuple-protocol case), it is treated as naming that reference; if it refers to an array element or class member, it is treated as evaluating `e[i]` or `e.m`, where `e` is the unnamed variable introduced by the structured binding declaration.

```cpp
#include <tuple>
struct S {
  mutable int m;
  constexpr S(int m) : m(m) {}
  virtual int g() const;
};
void f(std::tuple<S&> t) {
  auto [r] = t;
  static_assert(r.g() >= 0);        // error: the dynamic type of r is unknown
  constexpr auto [m] = S(1);
  static_assert(m == 1);            // error: equivalent to e.m, reads a mutable member
  using A = int[2];
  constexpr auto [v0, v1] = A{2, 3};
  static_assert(v0 + v1 == 5);      // OK: equivalent to e[0] + e[1]
}
```

constexpr structured bindings themselves are a new C++26 feature ([[P2686]]).

## Remaining items

- ¶2.26–¶2.27 `co_await` and `co_yield` are not allowed. A coroutine frame requires run-time allocation, and coroutines are not constexpr-suitable functions.
- ¶2.32 {{c++26}} An expression that produces an injected declaration (for example `std::meta::define_aggregate`) may only appear in a `consteval { ... }` block, so that operations modifying the program itself have a definite place and time. See [[expr.const.reflect]].
- ¶2.33 An *asm-declaration* cannot be evaluated. Since C++20 it can be written in a constexpr function, for use in the run-time branch of `std::is_constant_evaluated()` or `if consteval`.
- ¶2.34 `va_arg` is not allowed; for `va_start`, see paragraph 4 above.
- ¶2.35 A **non-constant library call** ([[g:non-constant-library-call|non-constant library call]]) is not allowed, i.e. a call that the library specification says prevents an expression from being constant, such as a call that doesn't meet its *Constant When* condition.
- ¶2.36 A `goto` statement is not allowed. Note 2 explains that this doesn't cover the statements whose semantics the standard describes in terms of goto (such as `while`).

```cpp
constexpr int gt(int n) {
  if (n < 0) goto bad;     // may be written since C++23
  return n;
bad:
  return 0;
}
constexpr int a = gt(1);     // OK: the goto is not executed
constexpr int b = gt(-1);    // error
```

`goto` is forbidden mainly for implementation cost: constant evaluators are usually interpreters running over the syntax tree, arbitrary jumps are hard to support, and anything `goto` can do can be done with structured control flow.

## Implementation view

!!! impl "The constant evaluator is an interpreter"
    Clang's constant evaluator has traditionally been an interpreter running over the AST (`ExprConstant.cpp`). It records the type, lifetime and active union member of every object, and represents pointers as an object plus a path, so it can detect out-of-bounds access, dangling and type punning precisely; a new bytecode interpreter (`-fexperimental-new-constant-interpreter`) is gradually replacing it. GCC's `constexpr.cc` also evaluates on the AST.

    In implementations like these, pointers are not integers but symbolic object-plus-offset values; there are no addresses in the evaluator at all. That is why `reinterpret_cast`, pointer-to-integer conversion and ordering the addresses of unrelated objects cannot be supported.

## Common misconceptions

!!! pitfall "UB in a constexpr function is always caught"
    The same `add(INT_MAX, 1)` is a compile error in `constexpr int x = ...` and run-time UB in `int x = ...`, where the compiler gives no hint at all. A constexpr function passing `static_assert` tests only shows that the tested sets of arguments have no UB.

!!! pitfall "Not being constant means compilation fails"
    Where a constant is not required, for example `const int n = f();` or `int x = f();` at namespace scope, an expression that isn't constant just means the initialization happens at run time instead, and the program is still valid. To make sure something is computed at compile time, write `constexpr` or `constinit`.

## Questions

!!! question "Question 1"
    Which of the following `static_assert`s are valid?

    ```cpp
    struct P { int x; constexpr int get() const { return 7; } };
    void f(P& r, P v) {
      static_assert(r.get() == 7);   // (a)
      static_assert(v.get() == 7);   // (b)
      static_assert(&r == &r);       // (c)
      static_assert(v.x == v.x);     // (d)
    }
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Valid. By paragraph 9, `r` is treated as bound to an unspecified `P` object; `get` is a constexpr function called during the evaluation and may use `this` (item 2.1.1), and it reads no members.
- (b) Valid. `v` is an object from outside the evaluation and is likewise treated as a specific instance.
- (c) Valid. Both sides refer to the same instance, taking the address reads no value, and the result is true.
- (d) Invalid. Reading `v.x` is an lvalue-to-rvalue conversion on an object that is neither usable in constant expressions nor created by this evaluation (item 2.10).

Before P2280, (a) and (c) were invalid too, because they required evaluating the reference `r`. Clang 23's results match the analysis above.
</details>

!!! question "Question 2"
    Why is `a` valid but `b` not?

    ```cpp
    constexpr int f(int* p) { return p ? *p : 0; }
    constexpr int a = f(nullptr);
    int g = 1;
    constexpr int b = f(&g);
    ```

<details markdown="1">
<summary>Answer</summary>

`f(nullptr)` doesn't execute `*p`, and the list only looks at operations actually executed. In `f(&g)`, `&g` itself is fine (`g` has static storage duration, so its address is a constant), but `*p` reads the value of `g`, and `g` is not const, not usable in constant expressions, and not created by this evaluation, which hits item 2.10.
</details>

!!! question "Question 3"
    `constexpr std::string s = "hi";` compiles with libc++, but a long string doesn't. Why? Is this code portable?

<details markdown="1">
<summary>Answer</summary>

The small string optimization (SSO) stores short strings inside the `std::string` object without allocating, so the initialization of `s` involves no dynamic allocation. A long string has to allocate heap memory, which is not freed by the end of the evaluation, violating item 2.20.

The standard specifies neither whether SSO is used in constant evaluation nor its capacity, so this code is not portable. libc++ (shipped with Clang 23) accepts `"hi"` and rejects strings longer than the SSO capacity.
</details>

## Summary

| What you want to do in constant evaluation | When it is allowed | Item |
|---|---|---|
| Read an object | It is usable in constant expressions, or was created by this evaluation | ¶2.10 |
| Modify an object | It was created by this evaluation | ¶2.18 |
| Call a function | constexpr, defined, not a coroutine | ¶2.3–¶2.5 |
| Call a virtual function, `dynamic_cast`, polymorphic `typeid` | The dynamic type is known | ¶2.6, ¶2.30 |
| `new` / `delete` | Paired within this evaluation | ¶2.20–¶2.23 |
| Placement new | The storage was obtained by this evaluation {{c++26}} | ¶2.20.2 |
| `static_cast` from `void*` | The object pointed to has a type similar to the target {{c++26}} | ¶2.15 |
| Throw an exception | Thrown and fully handled within this evaluation {{c++26}} | ¶2.24–¶2.25 |
| `reinterpret_cast`, `goto`, `asm`, `co_await` | Never, once evaluated | ¶2.16, ¶2.36, ¶2.33, ¶2.26 |
| Core-language UB, erroneous behavior | Never; must be diagnosed | ¶2.8 |
| Library UB | Unspecified | ¶4 |
| `[[assume]]` false | Implementation-defined | ¶3 |
