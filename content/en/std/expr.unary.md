---
title: Unary expressions
summary: "Operators written before their operand: indirection, address-of, unary + - ! ~, prefix increment and decrement, plus what operands sizeof, alignof and the noexcept operator require and what results they give."
updated: 2026-10-19
---

!!! tldr
    - `*p` requires `p` to really point to an object or function; null, dangling and past-the-end pointers are all UB, and in C++ `&*p` doesn't rescue it.
    - Only an explicit `&` applied to an unparenthesized qualified name (`&S::m`) gives a pointer to member; `&(S::m)` and `&m` are ordinary pointers.
    - `+ - ~` apply integral promotion first: `-(unsigned short)1` is the `int` −1, and `~(unsigned char)0` is the `int` −1. Negating an unsigned value is defined; signed overflow is UB.
    - The operands of `sizeof` and `noexcept` are unevaluated, but a prvalue operand is still materialized into a temporary, so its destructor must be usable too.
    - `noexcept(e)` looks only at declared exception specifications; it answers whether `e` can throw, not whether it can go wrong.

Unary expressions (*unary-expression*) are the most varied group in Chapter 7: besides `* & + - ! ~` and prefix `++ --`, `sizeof`, `alignof`, `noexcept`, `co_await`, `new`, `delete` and the reflection operator `^^` are all unary expressions in the grammar. The last few have a lot of content and get their own pages: [[expr.await|co_await]], [[expr.new|new]], [[expr.delete|delete]], [[expr.reflect|^^]].

A few concepts are used throughout: **value categories** (lvalue, prvalue, etc.; see [[topics/value-categories]]), **integral promotion** (converting integer types narrower than `int` to `int` or `unsigned int` first, [[g:integral-promotion]]) and **unevaluated operands** (operands that only take part in type checking and are not executed at run time, [[g:unevaluated-operand]]).

## Grouping and grammar [expr.unary.general]

```cpp ok
int x = 3;
int* p = &x;
int a = - - x;       // -(-x) == 3
int b = *&*p;        // *(&(*p)) == 3
bool c = !~x;        // !(~3) == false
auto d = -(long)x;   // the operand can be a C-style cast
```

¶1 Unary operators group right to left. In the grammar, the operand of `* & + - ! ~` and prefix `++ --` is a *cast-expression*, so `-(long)x` and `*(T*)p` need no extra parentheses.

`sizeof` is different: its operand is a *unary-expression* or a parenthesized type name. `sizeof (int)x` is not read as `sizeof((int)x)`: `sizeof (int)` is matched first as the size of a type, and the leftover `x` makes the whole expression ill-formed.

```cpp error
int x = 3;
auto s = sizeof (int)x;   // error: an extra x after sizeof(int)
```

## Indirection: unary `*` [expr.unary.op]

¶1 Unary `*` performs **indirection** ([[g:indirection]]), commonly called dereferencing. The operand must be a prvalue pointer to an object type or function type `T`, and the result is an lvalue of type `T`.

If the pointer points to an object or function, the result denotes it; otherwise the behavior is undefined. Null, dangling and past-the-end pointers all fall under "doesn't point to an object". The only exception is `typeid(*p)`: when `p` is null and `*p` has polymorphic class type, `std::bad_typeid` is thrown ([[expr.typeid]]).

<div class="compare" markdown="1">

```cpp ok
struct Inc;          // incomplete type
Inc& f(Inc* p) {
  return *p;   // OK: only used to bind a reference
}
```

```cpp run ub
int main() {
  int* p = nullptr;
  int& r = *p;  // UB: p doesn't point to an object
  (void)r;
}
```

</div>

Two notes carve out valid but limited uses. Note 1: indirection through a pointer to an object outside its lifetime is itself valid, and the resulting lvalue can only be used in the limited ways allowed by [[basic.life]]. Note 2: indirection through a pointer to an incomplete type is also valid; the result can be bound to a reference and have its address taken, but its value can't be read (no lvalue-to-rvalue conversion, [[conv.lval]]). `void*` can't be dereferenced, because `void` is not an object type.

!!! lawyer "Is `&*p` UB for a null pointer?"
    C specifies that `&*p` is equivalent to `p` and that the `*` is not evaluated. C++ has no such rule: by the letter of ¶1, `*p` itself is UB when `p` is null. A proposal to allow empty lvalues was discussed in [[CWG232]] for years and never adopted. So in C++, write `p` or `std::to_address(p)`. Likewise, for an array `a` of `N` elements, `&a[N]` is `&*(a + N)`, which by the letter is indirection through a past-the-end pointer; to get a past-the-end pointer, write `a + N`.

## Address-of: unary `&` [expr.unary.op]

¶2 The results of `&`, `+`, `-`, `!` and `~` are all prvalues.

¶3 The operand of `&` must be an lvalue, so `&42` and `&f()` (with `f` returning a non-reference type) are ill-formed. Taking the address of a variable of type `cv T` gives `cv T*`, keeping the cv-qualification (Note 4).

A single object can be treated as an array of one element ([[expr.add]]), so in Example 1 `&a + 1` is a valid past-the-end pointer, and comparing it with `&a` is defined.

### When you get a pointer to member (¶3.1, ¶4)

```cpp ok
struct S {
  int m;
  void f() {
    int S::* pm = &S::m;   // pointer to member
    int* p = &(S::m);      // ordinary pointer: &this->m
    int* q = &m;           // ordinary pointer: &this->m
    (void)pm; (void)p; (void)q;
  }
};
```

In a member function, both `S::m` and `m` can denote a member of the current object (with an implied `this->`), so `&S::m` could mean two things. ¶4 says a pointer to member is formed only when `&` is written explicitly and its operand is an unparenthesized qualified name (*qualified-id*, or a C++26 *splice-expression*). All other forms are treated as ordinary expressions:

| Form | Result |
|---|---|
| `&S::m` | Pointer to member `int S::*` |
| `&(S::m)` | Ordinary pointer. Inside a member function `S::m` means `(*this).m` ([[expr.prim.id]]); ill-formed outside |
| `&m` | Ordinary pointer `&this->m`; ill-formed for member functions |
| `S::f` (no `&`) | A non-static member function doesn't implicitly convert to a pointer the way an ordinary function does |

¶3.1 The type of a pointer to member is `T C::*`, where `C` is the class in which the member is declared, not the class written before the `::`:

```cpp ok
#include <type_traits>
struct A { int i; };
struct B : A { };
static_assert(std::is_same_v<decltype(&B::i), int A::*>);
int B::* pb = &B::i;   // OK: int A::* implicitly converts to int B::* ([conv.mem])
```

Note 5: a pointer to member formed from a `mutable` data member doesn't carry the `mutable` property; accessing it through a `const` object with `.*` gives a `const` result.

### Explicit object member functions (¶3.2)

C++23's explicit object member functions (`void g(this S&)`, commonly called deducing this) behave more like ordinary functions in terms of calling convention. Taking their address requires a qualified name, and the result is an ordinary function pointer, not a pointer to member function:

<div class="compare" markdown="1">

```cpp ok
#include <type_traits>
struct S {
  void g(this S&) {}
  void h() {}
};
static_assert(std::is_same_v<
  decltype(&S::g), void (*)(S&)>);
static_assert(std::is_same_v<
  decltype(&S::h), void (S::*)()>);
```

```cpp error
struct S {
  void g(this S&);
  void f();
};
void S::f() {
  auto x = &g;  // error: must write &S::g
}
```

</div>

### Overloaded `operator&` and bit-fields (¶5)

Classes can overload unary `&` ([[over.oper]]), so `&x` isn't necessarily the address of `x`. Generic code that needs the real address should use `std::addressof`, which bypasses a user-defined `operator&` and is also usable in constant evaluation.

```cpp run ok
#include <memory>
struct Evil { Evil* operator&() const { return nullptr; } };

int main() {
  Evil e;
  Evil* p1 = &e;                  // calls Evil::operator&, gets nullptr
  Evil* p2 = std::addressof(e);   // the real address
  return (p1 == nullptr && p2 != nullptr) ? 0 : 1;
}
```

¶5 If `&` is applied to an lvalue of incomplete class type and the class, once complete, declares `operator&`, it is unspecified whether the built-in meaning or the overload is used. The reason is that the compiler can't see that overload when it processes `&x`.

The same paragraph says the operand of `&` can't be a bit-field: a bit-field doesn't necessarily start on a byte boundary and has no address ([[class.bit]]).

```cpp error
struct BF { int b : 3; };
void f(BF& x) { auto p = &x.b; }   // error: can't take the address of a bit-field
```

### Address of an overload set (¶6)

¶6 is a note: taking the address of an overloaded function name is only possible in a context that uniquely determines the target function, such as initializing a function pointer ([[over.over]]). The context may select either a static or a non-static member function, so the same `&M::s` can be an ordinary function pointer or a pointer to member function:

```cpp ok
void over(int) {}
void over(double) {}
struct M {
  static void s(int) {}
  void s(double) {}
};
void (*pf)(double) = &over;      // the target type picks over(double)
void (*ps)(int) = &M::s;         // static member selected: ordinary function pointer
void (M::*pm)(double) = &M::s;   // non-static member selected: pointer to member function
```

## Arithmetic unary operators `+ - ! ~` [expr.unary.op]

### Unary `+` (¶7)

¶7 The operand must be a prvalue of arithmetic, unscoped enumeration or pointer type, and the result is its value. Integral and enumeration operands undergo integral promotion first, and the result type is the promoted type.

Unary `+` looks like it does nothing, but it has two common uses. `+c` (with `c` a `char`) gives an `int`, making `std::cout << +c` print the numeric value instead of the character. When the operand has class type, the built-in candidate `T* operator+(T*)` triggers the class's conversion function ([[over.built]]); that is how `+[]{ ... }` turns a captureless lambda into a function pointer.

```cpp ok
#include <type_traits>
static_assert(std::is_same_v<decltype(+'a'), int>);       // integral promotion
auto fp = +[](int x) { return x * 2; };                   // closure → function pointer
static_assert(std::is_same_v<decltype(fp), int (*)(int)>);
int arr[3];
static_assert(std::is_same_v<decltype(+arr), int*>);      // the array is converted to a pointer first
```

Scoped enumerations (`enum class`) are not allowed; `+E::a` is ill-formed.

### Unary `-` (¶8)

¶8 The operand must be a prvalue of arithmetic or unscoped enumeration type, not a pointer. Integer operands are promoted first.

Negating an unsigned value is defined: the result is 2ⁿ minus the operand's value, where n is the number of bits of the promoted type (Note 8: i.e. two's complement negation). So `-1u == UINT_MAX` is portable.

The thing to watch is promotion. `unsigned short` and `unsigned char` are usually promoted to `int`, so negation becomes a signed operation:

```cpp ok
#include <climits>
#include <type_traits>
static_assert(-1u == UINT_MAX);
static_assert(std::is_same_v<decltype(-(unsigned short)1), int>);
static_assert(-(unsigned short)1 == -1);    // signed -1, not 65535
```

Signed values don't wrap around: the mathematical result of `-INT_MIN` can't be represented in `int`, which is UB by [[expr.pre#4]].

```cpp run ub
#include <climits>
int main(int argc, char**) {
  int x = INT_MIN + argc - 1;   // INT_MIN at run time
  return -x;                    // UB: the result can't be represented in int
}
```

Running it with Clang 23 and `-fsanitize=undefined`, UBSan reports `negation of -2147483648 cannot be represented in type 'int'`.

Unsigned types are modulo-2ⁿ arithmetic to begin with ([[basic.fundamental]]), and negation is just one of their operations. Signed overflow is UB so that the optimizer can do algebraic simplifications. C++20 specifies two's complement representation for signed integers, but didn't make overflow defined.

### Logical negation `!` (¶9)

¶9 The operand of `!` is **contextually converted to `bool`** ([[g:contextually-converted-to-bool]]), which works like `bool t(e);`, so `explicit operator bool` can be used. The result type is `bool`.

```cpp ok
struct Flag { explicit operator bool() const { return true; } };
Flag f;
bool b = !f;     // OK: contextual conversion can use explicit conversion functions
bool d = !!f;    // a common idiom for converting to bool
// bool c = f;   // error: copy-initialization doesn't consider explicit conversion functions
```

### Bitwise complement `~` (¶10)

¶10 The operand must be a prvalue of integral or unscoped enumeration type; it undergoes integral promotion first, and every bit of the result is the opposite of the operand's. Integers use two's complement representation, so `~x == -x - 1` holds for signed values too, and never overflows.

Promotion brings surprises here too: `~uc` (with `uc` an `unsigned char`) has type `int`, with all the high bits set.

```cpp ok
unsigned char uc = 0x0F;
auto r = ~uc;                                          // int, value -16
unsigned char back = static_cast<unsigned char>(~uc);  // 0xF0, needs explicit truncation
static_assert(~0 == -1);
```

The end of ¶10 resolves a grammatical ambiguity. When `~` is followed by a type name (or a *computed-type-specifier* such as `decltype(x)`), it could be read either as unary `~` or as the start of a destructor name. The standard says it is treated as the operator:

```cpp ok
struct X {
  int operator~() const { return 1; }
  void f() {
    ~X();          // calls X::operator~ on the temporary X(), not a destructor
    this->~X();    // after -> it can only be a destructor name
  }
};
```

Note 10 explains why there is no ambiguity after `.`, `->` and `::`: the grammar doesn't allow an operator to follow those tokens directly, so `p->~X()` and `X::~X` are always destructor names.

## Prefix increment and decrement [expr.pre.incr]

¶1 `++x` is equivalent to `x += 1`, and `--x` to `x -= 1` ([[expr.assign]]). It follows that the operand must be a modifiable lvalue and the result is an lvalue too. The result of postfix `x++`, by contrast, is a prvalue ([[expr.post.incr]]).

<div class="compare" markdown="1">

```cpp ok
int i = 0;
int& r = ++i;     // the result is an lvalue
int& s = ++++i;   // ++(++i), i == 3
double d = 0.5;
double& t = --d;  // floating point works too
```

```cpp error
void f() {
  bool b = false;
  ++b;           // error: the operand is bool
  int i = 0;
  int& r = i++;  // error: the postfix result is a prvalue
}
```

</div>

The operand can't be `cv bool`. C++98 allowed `++b` (which set it to `true`), but it was deprecated from the start, and C++17 removed it {{removed:C++17}}; `--b` was never valid.

Using an operand of volatile type is deprecated (C++20, [[depr.volatile.type]]). `++v` looks like one operation but is really a read and a write, neither atomic nor a single volatile access. Clang 23 gives a `-Wdeprecated-volatile` warning for it by default.

## sizeof [expr.sizeof]

### What the result is (¶1, ¶5)

¶1 `sizeof` gives the number of bytes occupied by a **non-potentially-overlapping** object of the operand's type. Potentially-overlapping subobjects are base class subobjects and `[[no_unique_address]]` members ([[g:potentially-overlapping-subobject]]); they can be smaller than a complete object of the same type, so they are excluded.

The operand can be written in two ways: an expression, which is an unevaluated operand; or a parenthesized type name.

```cpp ok
int i = 0;
auto n = sizeof(i++);   // i is not incremented: the operand is not evaluated
int runtime_value();
constexpr auto k = sizeof(runtime_value());   // the function isn't called; the result is still a constant
```

¶5 The result is a prvalue of type `std::size_t` and is an integral constant expression (Note 3). It doesn't matter that the expression in the operand isn't itself constant, because it is never evaluated. Clang warns for `sizeof(i++)` that an expression with side effects has no effect in an unevaluated context.

The `sizeof` of a narrow character type (`char`, `signed char`, `unsigned char`, `char8_t`, [[g:narrow-character-type]]) is 1. The `sizeof` of every other fundamental type is implementation-defined, including `bool`, `wchar_t`, `char16_t` and `char32_t`; a footnote specifically points out that `sizeof(bool)` is not required to be 1.

The following are ill-formed: an operand of function type or incomplete type, or such a type name; an operand that is an expression designating a bit-field.

```cpp error
struct Inc;
void f();
struct BF { int b : 3; };
auto a = sizeof(Inc);       // error: incomplete type
auto b = sizeof(f);         // error: function type (doesn't decay to a pointer, see below)
auto c = sizeof(BF{}.b);    // error: bit-field
auto d = sizeof(void);      // error: void is an incomplete type
```

### References, classes and arrays (¶2)

```cpp ok
struct Empty {};
struct Holder { [[no_unique_address]] Empty e; int x; };
static_assert(sizeof(Empty) == 1);             // a complete object is at least 1 byte
static_assert(sizeof(Holder) == sizeof(int));  // e overlaps x (Itanium ABI)
static_assert(sizeof(Holder::e) == 1);         // subobject: still reports the size of Empty
static_assert(sizeof(int&) == sizeof(int));
static_assert(sizeof(char[10]) == 10);
```

¶2 For a reference type, the result is the size of the referenced type. For a reference variable `r`, `sizeof(r)` is the same, because the expression `r` never has reference type in the first place ([[expr.type]]).

For a class, the result includes the trailing padding needed to place objects in an array. The `sizeof` of an empty class is at least 1, because every complete object occupies at least one byte ([[intro.object]]). Applying `sizeof` to a potentially-overlapping subobject gives the size of its type, not the space the subobject actually occupies.

For an array, the result is the number of bytes in the whole array, i.e. the number of elements times the element size, with no extra padding between elements.

`sizeof(Holder) == sizeof(int)` depends on how the implementation handles `[[no_unique_address]]`: it holds under the Itanium ABI; MSVC ignores this attribute by default, and you have to write `[[msvc::no_unique_address]]`.

### Conversions that are not applied (¶3)

¶3 The lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are not applied to the operand of `sizeof`. So `sizeof(arr)` gives the size of the whole array, and `sizeof(f)` is ill-formed rather than giving the size of a function pointer.

!!! pitfall "sizeof of an array parameter"
    When a function parameter is written as `int a[10]`, its type is adjusted to `int*` at the declaration ([[dcl.fct]]), and `sizeof(a)` gives the size of a pointer. Clang has a `-Wsizeof-array-argument` warning for this. To keep the length, pass a reference `int (&a)[10]` or use `std::span`.

If the operand is a prvalue, the **temporary materialization conversion** ([[g:temporary-materialization-conversion]]) is applied, i.e. a temporary object is conceptually created. The temporary is never actually created, but its destructor must be usable:

<div class="compare" markdown="1">

```cpp error
struct D { D(); ~D() = delete; };
D make();
auto s = sizeof(make());
// error: materialization requires a usable destructor
```

```cpp ok
struct D { D(); ~D() = delete; };
D make();
using T = decltype(make());
// OK: decltype doesn't materialize
```

</div>

[[dcl.type.decltype#2]] explicitly says a prvalue operand of `decltype` is not materialized; `sizeof` has no such exemption.

!!! note "Is `sizeof(int())` an expression or a type?"
    Up to C++23, the type in `sizeof ( type-id )` could be a function type. By the rule that whatever can be read as a type is read as a type ([[dcl.ambig.res]]), `sizeof(int())` takes the size of the function type `int()` and is ill-formed. The current draft changed this position to a *nofun-type-id* (a type name that can't be a function type, [[g:nofun-type-id]]), so `int()` can only be an expression, `sizeof(int())` equals `sizeof(int)`, and the example in [[dcl.ambig.res#2]] is annotated that way. This is new wording after C++23. As of this writing, Clang 23 still follows the old grammar and reports `invalid application of 'sizeof' to a function type`.

### sizeof... (¶4)

¶4 The `id` in `sizeof...(id)` must be a pack ([[g:pack]]), and the result is the number of elements in the pack ([[temp.variadic]]). It counts as a pack expansion itself, so no further `...` is needed.

```cpp ok
#include <cstddef>
template<class... Ts>
constexpr std::size_t count = sizeof...(Ts);
static_assert(count<> == 0);
static_assert(count<int, char, double> == 3);

template<class... Ts>
constexpr std::size_t bytes = (sizeof(Ts) + ... + 0);   // contrast: sizeof of each element, then fold
static_assert(bytes<char, char> == 2);
```

## alignof [expr.alignof]

```cpp ok
struct alignas(32) V { float f[8]; };
static_assert(alignof(char) == 1);
static_assert(alignof(V) == 32);
static_assert(alignof(V&) == 32);                // reference → referenced type
static_assert(alignof(V[4]) == 32);              // array → element type
static_assert(alignof(int[]) == alignof(int));   // arrays of unknown bound work too
```

¶1 `alignof` gives the alignment requirement of its operand type ([[basic.align]]). The operand can only be a parenthesized type name denoting a complete object type, an array of one, or a reference to either. ¶2 The result is an integral constant of type `std::size_t`. ¶3 For a reference type, the result is the alignment of the referenced type; for an array type, the alignment of the element type.

Unlike `sizeof`, standard `alignof` only accepts types, not expressions. GCC and Clang accept `alignof(expr)` as an extension, and Clang warns under `-pedantic` with `'alignof' applied to an expression is a GNU extension`. The portable form is `alignof(decltype(expr))`. `decltype` of a parenthesized expression gives a reference type, but fortunately ¶3 makes a reference give the same result as the referenced type:

```cpp ok
int x;
static_assert(alignof(decltype(x)) == alignof(decltype((x))));   // int and int&
```

```cpp error
struct Inc;
auto a = alignof(Inc);      // error: incomplete type
auto b = alignof(void());   // error: function type
```

`std::alignment_of_v<T>` is defined as `alignof(T)`; there is no difference between them.

## The noexcept operator [expr.unary.noexcept]

¶1 The operand of `noexcept(e)` is an unevaluated operand. As with `sizeof`, a prvalue operand undergoes temporary materialization, so the temporary's destructor counts too.

¶2 The result is an integral constant of type `bool`: `false` if the full-expression of the operand is **potentially-throwing** ([[g:potentially-throwing-expression]]), `true` otherwise.

[[except.spec#6]] defines which expressions are potentially-throwing:

| Item | Case | Example |
|---|---|---|
| ¶6.1 | A call to a function whose exception specification is potentially-throwing | `f()`, with `f` not declared `noexcept` |
| ¶6.2 | An implicit call to a potentially-throwing function | Overloaded operators, the allocation function of a *new-expression*, destructors |
| ¶6.3 | A *throw-expression* | `throw 1` |
| ¶6.4 | A `dynamic_cast` to a reference that requires a runtime check | `dynamic_cast<D&>(b)` |
| ¶6.5 | `typeid` applied to the built-in `*` of a pointer to a polymorphic class | `typeid(*p)` |
| ¶6.6 | Any evaluated immediate subexpression is potentially-throwing | `g() + f()` |

```cpp ok
#include <typeinfo>
void f();
void g() noexcept;
struct T { ~T() noexcept(false); };
T make() noexcept;
struct P { virtual ~P(); };
struct Q : P {};
extern P* pp;
extern int zero;

static_assert(!noexcept(f()));                    // ¶6.1
static_assert(noexcept(g()));
static_assert(noexcept(f));                       // only names the function, no call
static_assert(!noexcept(new int));                // ¶6.2: the allocation function may throw bad_alloc
static_assert(!noexcept(make()));                 // the temporary's destructor is potentially-throwing
static_assert(!noexcept(dynamic_cast<Q&>(*pp)));  // ¶6.4
static_assert(noexcept(dynamic_cast<Q*>(pp)));    // the pointer form returns null on failure, doesn't throw
static_assert(!noexcept(typeid(*pp)));            // ¶6.5
static_assert(noexcept(1 / zero));                // division by zero is UB, not an exception
static_assert(noexcept(sizeof(make())));          // the operand of sizeof is not evaluated
```

A few things can be seen from this example. Only the declaration matters: even if `f`'s body never throws, without `noexcept` the result is `false`. The full-expression includes destruction of temporaries, so although `make()` itself is `noexcept`, `noexcept(make())` is still `false`. UB is not an exception: `noexcept(1 / zero)` is `true`.

### Conditional noexcept

The `noexcept` operator most often appears inside an exception specification, written `noexcept(noexcept(...))`: the outer one is the specifier, the inner one the operator.

```cpp ok
#include <utility>
template<class T>
void my_swap(T& a, T& b)
    noexcept(noexcept(T(std::move(a))) && noexcept(a = std::move(b)))
{
  T tmp(std::move(a));
  a = std::move(b);
  b = std::move(tmp);
}

struct Throwy { Throwy(Throwy&&); Throwy& operator=(Throwy&&); };
static_assert(noexcept(my_swap(std::declval<int&>(), std::declval<int&>())));
static_assert(!noexcept(my_swap(std::declval<Throwy&>(), std::declval<Throwy&>())));
```

When `std::vector` grows, it uses `std::move_if_noexcept` to decide between moving and copying, based on exactly this kind of check: if the move constructor is potentially-throwing and the type is copyable, it falls back to copying to keep the strong exception guarantee.

!!! pitfall "`noexcept(T(std::move(a)))` also counts the destructor"
    `T(std::move(a))` is a prvalue, and after materialization the temporary's destructor counts. If `T`'s destructor is `noexcept(false)`, the result is `false` even when the move constructor is `noexcept`. To check only the construction, use `std::is_nothrow_move_constructible_v<T>`.

## Implementation view

!!! impl "Compilers and ABI"
    - `sizeof`, `alignof` and `noexcept` are all computed as constants in the front end and generate no code. `-fno-exceptions` doesn't change the result of the `noexcept` operator.
    - The sizes of fundamental types are part of the ABI: on x86-64 Linux/macOS `long` is 8 bytes, on Windows x64 it is 4; `wchar_t` is 4 bytes on Linux/macOS and 2 on Windows.
    - Both libc++ and libstdc++ implement `std::addressof` with the compiler builtin `__builtin_addressof`, so it both bypasses overloads and works in constant evaluation.
    - In the Itanium ABI, a pointer to data member is an offset, with null represented as −1 (offset 0 is a valid value); a pointer to member function occupies two words: the function address (or vtable offset plus 1) and the `this` adjustment. MSVC uses representations of different sizes depending on the class's inheritance model.

## History and evolution

!!! history
    - C++11 added `alignof`, the `noexcept` operator and `sizeof...`, and `sizeof` could be applied directly to non-static data members (`sizeof(S::m)`).
    - C++17 removed `++` on `bool`; exception specifications became part of the function type, so `noexcept(fp())` can decide from the function pointer's type.
    - C++20 specified two's complement representation for integers and deprecated prefix increment and decrement of volatile operands.
    - C++23's explicit object member functions brought the rule in ¶3.2 that their address must be taken with a qualified name.
    - C++26 added *splice-expression* to ¶3.1 and ¶4, treated the same as qualified names {{c++26}}.

## Common misconceptions

!!! pitfall "Thinking `-u` is always an unsigned operation"
    Unsigned types narrower than `int` are promoted to `int` first. `-(unsigned short)1` is the `int` −1; `~(unsigned char)0` is the `int` −1, not 255.

!!! pitfall "Thinking `sizeof` evaluates its operand"
    `sizeof(f())` doesn't call `f`, and `sizeof(i++)` doesn't change `i`. That is why a function that is only declared, never defined, can appear in `sizeof`.

!!! pitfall "Thinking `noexcept(e)` tells whether something can go wrong"
    It only answers whether an exception can be thrown. UB, `std::terminate` and assertion failures are outside its scope.

## Questions

!!! question "Question 1"
    Inside the member function `S::f` of `struct S { int m; void f(); };`, what are the types of `&S::m`, `&(S::m)`, `&m` and `&this->m`?

<details markdown="1">
<summary>Answer</summary>

`&S::m` is `int S::*`: an explicit `&` with an unparenthesized qualified name (¶3.1, ¶4). The other three are all `int*`: `(S::m)` is parenthesized and doesn't form a pointer to member; inside a member function it means `(*this).m` ([[expr.prim.id]]); `&m` uses an unqualified name, which Note 6 says is not a pointer to member; `&this->m` is an ordinary member access to begin with.
</details>

!!! question "Question 2"
    Does `static_assert(noexcept(std::declval<std::string>()));` pass?

<details markdown="1">
<summary>Answer</summary>

Yes. `std::declval<std::string>()` returns `std::string&&`, an xvalue rather than a prvalue, so there is no materialization and no temporary to destroy; `declval` itself is declared `noexcept`.
</details>

!!! question "Question 3"
    Let `unsigned short a = 65535;` with a 32-bit `int`. What are `-a`, `~a` and `a * a`? Which one has UB?

<details markdown="1">
<summary>Answer</summary>

All three first promote `a` to the `int` 65535. `-a` is the `int` −65535; `~a` is the `int` −65536; `a * a` is the `int` multiplication 65535 × 65535 = 4294836225, which exceeds the range of `int` and is UB ([[expr.pre#4]]).
</details>

## Summary

| Operator | Operand | Result | Key points |
|---|---|---|---|
| `*p` | Pointer to an object or function | lvalue of `T` | UB if it doesn't point to an object |
| `&x` | lvalue, not a bit-field | `T*` or `T C::*` | A pointer to member is formed only by `&C::m`; may be overloaded |
| `+x` `-x` `~x` | prvalue of arithmetic or integral type | The promoted type | Integral promotion first; unsigned negation is defined |
| `!x` | Contextually converted to `bool` | `bool` | `explicit operator bool` is usable |
| `++x` `--x` | Modifiable lvalue, not `bool` | lvalue | Equivalent to `x += 1` |
| `sizeof` | Expression (unevaluated) or type | `size_t` constant | References give the referenced type; prvalues are materialized |
| `sizeof...` | Pack | `size_t` constant | Is itself a pack expansion |
| `alignof` | Type | `size_t` constant | Only accepts types |
| `noexcept(e)` | Expression (unevaluated) | `bool` constant | Whether the full-expression is potentially-throwing |
