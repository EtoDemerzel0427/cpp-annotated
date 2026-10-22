---
title: Undefined behavior in [expr]
summary: "The 34 kinds of undefined behavior stated explicitly in Clause 7: overflow and division by zero, shifts, out-of-range floating and integer conversions, null and out-of-bounds pointers, strict aliasing and invalid value representations, wrong targets of the various casts, pointers to members, mismatched new and delete, and how each shows up under sanitizers and in constant evaluation."
updated: 2026-10-19
---

!!! tldr
    - UBSan catches nearly all the arithmetic undefined behavior (signed overflow, division by zero, `INT_MIN / -1`, shift counts that are negative or not less than the width), and constant evaluation always rejects it.
    - The result of pointer arithmetic may only land between indexes 0 and n of the same array; merely computing an out-of-bounds pointer is undefined behavior, without any dereference.
    - Accesses with the wrong type (strict aliasing, wrong `static_cast` downcasts, object type not matching the expression type) are mostly invisible to run-time tools, and their consequences often appear only once optimization is on.
    - The forms of new and delete must match; deleting through a base class pointer requires the base class to have a virtual destructor, and array delete does not allow polymorphism at all.
    - A floating-point conversion is undefined behavior only when the value is outside the range of the target type. IEEE 754 floating-point types can represent infinity, so `double` to `float` never triggers it, while floating to integer does.

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.3 subclause corresponds to Clause 7 [expr], and also includes the strict aliasing rule from [[basic.lval]]: 34 entries in all, the densest subclause for undefined behavior. Below they are grouped by topic rather than in annex order.

All run results below come from Clang 23 (arm64 macOS), compiled by default with `-O0 -g -fsanitize=address,undefined`, i.e. with both ASan (which checks memory accesses) and UBSan (which checks some undefined behavior) on. Two things about this environment are worth noting:

- On this platform `-fsanitize=undefined` does not include the `vptr` check (which checks the dynamic type of polymorphic objects); it has to be added with `-fsanitize=vptr`;
- On macOS, ASan does not check mismatched forms of new and delete by default; set the environment variable `ASAN_OPTIONS=alloc_dealloc_mismatch=1`.

Constant evaluation means putting the same operation into the initializer of a `constexpr` variable. Per [[expr.const.core]], the compiler must reject core language undefined behavior there, so this is the only means at the level of the standard that is guaranteed to find these errors.

## Arithmetic

### F.3.1 The result is mathematically undefined or outside the type's range {#expr.expr.eval}

`[ub:expr.expr.eval]` · main text [[expr.pre#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <limits>
#include <cstdio>

int main(int argc, char**) {
  int m = std::numeric_limits<int>::max() - 1 + argc;   // INT_MAX, known only at run time
  int x1 = m + 1;                                       // UB: 2147483647 + 1 is not representable
  int n = std::numeric_limits<int>::min() + argc - 1;
  int x2 = n / -argc;                                   // UB: -2147483648 / -1 is not representable
  std::printf("%d %d\n", x1, x2);
}
```

If during the evaluation of an expression the result is not mathematically defined or not in the range of representable values for its type, the behavior is undefined. This is the general source of signed integer overflow. Unsigned integers are unaffected; their arithmetic is defined modulo 2ⁿ ([[basic.fundamental]]).

At run time, UBSan reports both: `signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'` and `division of -2147483648 by -1 cannot be represented in type 'int'`. In constant evaluation `INT_MAX + 1` is rejected with `value 2147483648 is outside the range of representable values of type 'int'`.

### F.3.28 Division by zero {#expr.mul.div.by.zero}

`[ub:expr.mul.div.by.zero]` · main text [[expr.mul#4]]

```cpp ub
int f(int d) {
  return 1 / d;    // UB when d == 0
}

double g(double d) {
  return 1.0 / d;  // when d == 0.0, also UB according to the main text
}
```

If the second operand of `/` or `%` is zero, the behavior is undefined, for integers and floating-point alike. A comment in the annex's example says that `1.0 / 0.0` is not undefined behavior on systems whose floating-point types can represent infinity, but the main text [[expr.mul#4]] has no such exception. IEEE 754 producing `+inf` is the implementation's behavior, not a guarantee of the standard.

Running the integer version, UBSan reports `division by zero`. In constant evaluation both `f(0)` and `1.0 / 0.0` are rejected with `division by zero`. The latter is also caught by [[expr.const.core#2.9]]: a floating-point operation with finite operands whose result is not finite is not a constant expression in the first place.

### F.3.29 When the quotient is not representable, both a/b and a%b are undefined {#expr.mul.representable.type.result}

`[ub:expr.mul.representable.type.result]` · main text [[expr.mul#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <climits>
#include <cstdio>

int q(int a, int b) { return a / b; }
int r(int a, int b) { return a % b; }

int main() {
  std::printf("%d %d\n", q(INT_MIN, -1), r(INT_MIN, -1));   // UB: both of them
}
```

If the quotient `a/b` is representable in the result type, `(a/b)*b + a%b` equals `a`; otherwise both `a/b` and `a%b` are undefined behavior. For `int`, the only counterexample is `INT_MIN / -1`. The mathematical result of `INT_MIN % -1` is 0, perfectly representable, yet the standard still makes it undefined behavior. A common explanation: hardware usually computes the quotient and remainder with the same division instruction, and when the quotient overflows, the remainder is unavailable too.

At run time UBSan reports both, and the wording for the `%` is also `division of -2147483648 by -1 cannot be represented in type 'int'`; the program prints `-2147483648 0`. In constant evaluation `INT_MIN % -1` is rejected as well. On x86, the `idiv` instruction raises a division exception (SIGFPE) in this case; the `sdiv` on our arm64 machine does not trap and just yields `INT_MIN`.

### F.3.33 Shift count negative or not less than the width {#expr.shift.neg.and.width}

`[ub:expr.shift.neg.and.width]` · main text [[expr.shift#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int main(int argc, char**) {
  int s = 31 + argc;
  int y1 = 1 << s;       // UB: shift count 32 equals the width of int
  int y2 = 1 << -argc;   // UB: negative shift count
  int ok = 1 << 31;      // OK (since C++20): the result is INT_MIN
  std::printf("%d %d %d\n", y1, y2, ok);
}
```

The width here is that of the left operand after integral promotion, so `char c; c << 20` shifts an `int` and is fine. Since C++20, shifts of signed numbers are defined in terms of two's complement, and `-1 << 1` and `1 << 31` are no longer undefined behavior; the only case left is an out-of-range shift count.

At run time UBSan reports `shift exponent 32 is too large for 32-bit type 'int'` and `shift exponent -1 is negative`. In constant evaluation they are rejected with `shift count 32 >= width of type 'int' (32 bits)` and `negative shift count -1` respectively.

## Floating and integer conversions

The four rules in this group have the same form: a conversion whose source value is outside the range representable by the target type is undefined behavior. The key is how the range is computed. IEEE 754 floating-point types can represent ±∞, so every finite value falls within their range.

### F.3.6 Floating-point conversion with the source value outside the target's range {#conv.double.out.of.range}

`[ub:conv.double.out.of.range]` · main text [[conv.double#2]]

```cpp ub
#include <limits>

int main() {
  double d2 = std::numeric_limits<double>::max();
  float f = d2;   // not UB on IEEE 754 platforms (the implementation chooses between FLT_MAX and +inf)
  int i = d2;     // UB: see F.3.7, DBL_MAX cannot be represented as an int
}
```

When converting `double` to `float`, a value that can be represented exactly is converted exactly; a value between two adjacent representable values is converted to one of them, chosen by the implementation; otherwise the behavior is undefined. IEEE 754 `float` can represent +∞, so at worst any finite `double` falls between `FLT_MAX` and +∞, and the result is an implementation-defined choice. Only on floating-point formats without infinity is converting `DBL_MAX` to `float` undefined behavior.

At run time UBSan reports only the `int` line: `1.79769e+308 is outside the range of representable values of type 'int'`. Initializing a `constexpr float` with `DBL_MAX`, Clang accepts it, consistent with the analysis above.

### F.3.7 Floating to integer where the truncated value is not representable {#conv.fpint.float.not.represented}

`[ub:conv.fpint.float.not.represented]` · main text [[conv.fpint#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <limits>
#include <cstdio>

int main() {
  volatile double d = (double)std::numeric_limits<int>::max() + 1;
  int x1 = d;   // UB: 2147483648 cannot be represented as an int
  std::printf("%d\n", x1);
}
```

Converting floating to integer first discards the fractional part; if the truncated value does not fit in the target type, the behavior is undefined. This differs from conversions between integers, which since C++20 are always defined, with the result obtained by modular arithmetic.

At run time UBSan's `float-cast-overflow` check reports `2.14748e+09 is outside the range of representable values of type 'int'`. In constant evaluation, initializing a `constexpr int` with `1e300` is rejected with `value 1.0E+300 is outside the range of representable values of type 'const int'`.

### F.3.8 Integer to floating where the value is outside the floating type's range {#conv.fpint.int.not.represented}

`[ub:conv.fpint.int.not.represented]` · main text [[conv.fpint#2]]

```cpp ub
int main() {
  unsigned long long x2 = -1;   // OK: unsigned wraparound, gives 2⁶⁴−1
  float f = x2;                 // UB only on systems where float has no infinity and its maximum is less than 2⁶⁴−1
}
```

As with F.3.6, this can only trigger when the floating type's range is finite (no infinity). The largest finite IEEE 754 `float` is about 3.4×10³⁸, far larger than any 64-bit integer, so you will not meet this entry on mainstream platforms.

### F.3.17 Explicit floating-point conversion with the value outside the target's range {#expr.static.cast.fp.outside.range}

`[ub:expr.static.cast.fp.outside.range]` · main text [[expr.static.cast#9]]

```cpp ub
#include <cfloat>

void f() {
  double d = FLT_MAX;
  d *= 16;
  float f = static_cast<float>(d);   // UB only on systems where float cannot represent +inf
}
```

This is the `static_cast` version of F.3.6, with the same rule. On IEEE 754 platforms like ours, `static_assert(static_cast<float>(FLT_MAX * 16.0) > FLT_MAX)` passes in constant evaluation, and the result is +∞.

## Dereferencing and pointer arithmetic

### F.3.20 Indirection through a pointer that does not point to an object or function {#expr.unary.dereference}

`[ub:expr.unary.dereference]` · main text [[expr.unary.op#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int f(int* p) { return *p; }

int main() {
  return f(nullptr);   // UB: dereferencing a null pointer
}
```

`*p` requires `p` to point to an object or function, the only exception being the operand of `typeid` ([[expr.typeid]]). Neither a null pointer nor a past-the-end pointer (pointing just after the last element of an array) points to an object, so `*nullptr` and `*end` are undefined behavior, even if the result immediately has its address taken with `&`. This differs from C, where neither the `*` nor the `&` in `&*p` is evaluated.

A pointer to an object outside its lifetime may be used for indirection (note 1 in the main text); what can be done after that is governed by [[basic.life]], which is a different set of rules.

At run time UBSan reports `load of null pointer of type 'int'`, followed by ASan's `SEGV on unknown address 0x000000000000`. Constant evaluation rejects it with `dereferencing a null pointer is not allowed in a constant expression`.

### F.3.4 Evaluating a reference that can no longer refer to the object {#expr.type.reference.lifetime}

`[ub:expr.type.reference.lifetime]` · main text [[expr.type#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int main() {
  int* ip = new int(5);
  int& i = *ip;
  delete ip;
  std::printf("%d\n", i);   // UB: the object i refers to has been freed
}
```

An expression of reference type designates some object X. It designates X only if a pointer to X would be valid at that point; otherwise evaluating it is undefined behavior. After `delete ip`, pointers to that storage are all invalid pointer values ([[basic.compound]]), so `i` cannot be used either. The annex's example has just the statement `i;`, showing that no read of the value is needed: merely evaluating the reference is undefined behavior.

At run time ASan reports `heap-use-after-free`.

### F.3.30 Creating an out-of-bounds pointer {#expr.add.out.of.bounds}

`[ub:expr.add.out.of.bounds]` · main text [[expr.add#4.3]]

```cpp ub
static const int arrs[10]{};
static const int arrs2[10][10]{};

void f() {
  const int* end = arrs + 10;          // OK: past-the-end pointer
  const int* y = arrs + 11;            // UB: creating an out-of-bounds pointer
  const int (*z)[10] = arrs2 + 11;     // UB: same, the element type is int[10]
}
```

The result of adding an integer to or subtracting it from a pointer may only land between indexes 0 and n of the same array, where n is the past-the-end position. Merely computing an out-of-bounds pointer is undefined behavior; no dereference is needed. An object that is not an array element is treated here as an array of one element.

At run time nothing is reported. UBSan's `pointer-overflow` check only checks for address wraparound, and ASan only checks actual memory accesses; only when `arrs[10]` is actually read do UBSan's `bounds` check and ASan report anything. Constant evaluation rejects it at creation, with `cannot refer to element 11 of array of 10 elements in a constant expression`.

### F.3.31 Subtracting two pointers not into the same array {#expr.add.sub.diff.pointers}

`[ub:expr.add.sub.diff.pointers]` · main text [[expr.add#5.3]]

```cpp ub
#include <cstddef>

void f() {
  int x[2];
  int y[2];
  std::ptrdiff_t off = x - y;   // UB: x and y are different arrays
}
```

Running the same code and printing `off` reports nothing, and the result is `-8`, i.e. the two stack arrays are 8 `int`s apart. Constant evaluation rejects it; Clang's diagnostic is `arithmetic involving unrelated objects '&x[0]' and '&y[0]' has unspecified value`.

### F.3.32 Pointer type not similar to the array element type {#expr.add.not.similar}

`[ub:expr.add.not.similar]` · main text [[expr.add#6]]

```cpp ub
#include <cstddef>

struct S     { int i; };
struct T : S { double d; };

int sum(const S* s, std::size_t count) {
  int r = 0;
  for (const S* end = s + count; s != end; ++s)   // UB: s actually points to elements of a T[]
    r += s->i;
  return r;
}

int main() {
  T test[5]{};
  return sum(test, 5);
}
```

Pointer arithmetic moves in units of array elements. If `p` has type `T*` but the array element it actually points to has a type not similar to `T` ([[g:similar-types]], roughly: the same type after removing cv-qualification at every level), `p + 1` is undefined behavior. The most common form is iterating over an array of derived objects through a base class pointer.

The example in the main text shows how strict this rule is: reading once through `reinterpret_cast<unsigned int*>(arr + 1)` is valid, since corresponding signed and unsigned types can access each other; but a further `+ 1` is undefined behavior, because `unsigned int` is not similar to `int`.

Running it reports nothing. `sizeof(S)` is 4 and `sizeof(T)` is 16, so each `++s` advances only 4 bytes, and the later elements read the padding inside `T` and the bytes of the `double`.

## Aliasing and value representation

### F.3.2 Accessing an object through a disallowed type (strict aliasing) {#expr.basic.lvalue.strict.aliasing.violation}

`[ub:expr.basic.lvalue.strict.aliasing.violation]` · main text [[basic.lval#11]]

```cpp run ub flags="-std=c++2c -O2" cc=clang_trunk
#include <cstdio>

int foo(float* f, int* i) {
  *i = 1;
  *f = 0.f;    // UB: writing an int object through a glvalue of type float
  return *i;   // the compiler may assume *f did not change *i and return 1 directly
}

int main() {
  int x = 0;
  x = foo(reinterpret_cast<float*>(&x), &x);
  std::printf("%d\n", x);
}
```

An object may only be accessed through a glvalue whose type is similar to its dynamic type, the corresponding signed or unsigned type, or `char`, `unsigned char` or `std::byte` ([[g:type-accessible]]). This rule lets the compiler assume that an `int*` and a `float*` do not point to the same object.

Compiled with `-O0` it prints `0`, with `-O2` it prints `1`, and with `-O2 -fno-strict-aliasing` it prints `0` again: the optimization level changes the program's output. Neither ASan nor UBSan checks aliasing rules; Clang also has a TypeSanitizer (`-fsanitize=type`, not in the `undefined` group), which finds this problem in our tests, reporting `type-aliasing-violation` and explaining `WRITE of size 4 … with type float accesses an existing object of type int`.

### F.3.3 Invoking a union's default copy or move with an argument that is not a union object {#expr.basic.lvalue.union.initialization}

`[ub:expr.basic.lvalue.union.initialization]` · main text [[basic.lval#11]]

```cpp ub
union U { int x; };

void f() {
  alignas(U) char u[sizeof(U)] = {};
  U o = reinterpret_cast<U&>(u);   // UB: the argument does not refer to a U object
}
```

The default copy and move operations of a union copy the object representation (all the bytes of the object in memory) directly, without needing to know which member is active. The prerequisite is that the argument really is a union object of the same type within its lifetime.

Running it reports nothing.

### F.3.5 Lvalue-to-rvalue conversion of an object with an invalid value representation {#conv.lval.valid.representation}

`[ub:conv.lval.valid.representation]` · main text [[conv.lval#3]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstring>
#include <cstdio>

bool f() {
  bool b = true;
  char c = 42;
  std::memcpy(&b, &c, 1);
  return b;   // UB: 42 is not a valid value representation of bool
}

int main() {
  bool b = f();
  std::printf("%d %d\n", (int)b, b ? 1 : 0);
}
```

The lvalue-to-rvalue conversion reads an object's value. When reading, the object's bit pattern must be a valid value representation of its type ([[g:value-representation]]). `bool` is the classic example: in mainstream ABIs only 0 and 1 are valid representations.

At run time UBSan's `bool` check reports `load of value 42, which is not a valid value for type 'bool'`. In constant evaluation `std::bit_cast<bool>((unsigned char)42)` is rejected with `value 42 cannot be represented in type 'bool'`.

### F.3.34 Source and target storage of an assignment partially overlap {#expr.assign.overlap}

`[ub:expr.assign.overlap]` · main text [[expr.assign#7]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int main() {
  int x = 0x01020304;
  char* c = reinterpret_cast<char*>(&x);
  x = *c;   // UB: the source (the first byte of x) partially overlaps the target x
  std::printf("%d\n", x);
}
```

If the value being stored in an object is read from another object that overlaps the target's storage, the overlap must be exact and the two must have the same type, i.e. self-assignment `x = x`; otherwise the behavior is undefined. This lets the compiler implement assignment without considering overlap, much like the difference between `memcpy` and `memmove`.

Running it reports nothing and prints `4` (on little-endian, the first byte of `x` is `0x04`).

## Type conversions

### F.3.15 static_cast downcast of a reference when the object is not actually of the target type {#expr.static.cast.base.class}

`[ub:expr.static.cast.base.class]` · main text [[expr.static.cast#2]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct B { virtual ~B() = default; };
struct D1 : B {};
struct D2 : B { int x = 0; };

int main() {
  D1 d;
  B& b = d;
  D2& r = static_cast<D2&>(b);   // UB: b refers to the base class subobject of a D1
  return r.x;
}
```

`static_cast<D&>(b)` performs no run-time check; it assumes `b` really is a base class subobject of some D object and adjusts the address by the offset known at compile time. If the assumption is false, the behavior is undefined. When you need a run-time check, use `dynamic_cast`.

With `-fsanitize=vptr` added, UBSan reports `downcast of address … which does not point to an object of type 'D2'`. With only `address,undefined`, the report comes from the subsequent out-of-bounds read (ASan's `stack-buffer-overflow`). The `vptr` check only applies to polymorphic types; B in the annex's original example has no virtual functions, and then no tool at all can find the problem at run time. Constant evaluation rejects it with `cannot cast object of dynamic type 'D1' to type 'D2'`.

### F.3.18 static_cast downcast of a pointer when there is no object of the target type at that location {#expr.static.cast.downcast.wrong.derived.type}

`[ub:expr.static.cast.downcast.wrong.derived.type]` · main text [[expr.static.cast#10]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct B { virtual ~B() = default; };
struct D1 : B {};
struct D2 : B { int x = 0; };

int main() {
  B* bp = new D1;
  D2* p = static_cast<D2*>(bp);   // UB: the B that bp points to is not a subobject of a D2
  int r = p->x;
  delete bp;
  return r;
}
```

This is the pointer version of F.3.15. At run time the `vptr` check first reports `downcast of address … which does not point to an object of type 'D2'`, then `member access within address … which does not point to an object of type 'D2'`. Without `vptr`, ASan reports `heap-buffer-overflow` at `p->x`.

### F.3.16 Converting to an enumeration without a fixed underlying type, with the value out of range {#expr.static.cast.enum.outside.range}

`[ub:expr.static.cast.enum.outside.range]` · main text [[expr.static.cast#8]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

enum A { e1 = 1, e2 };   // the range of values is [0, 3]

int main(int argc, char**) {
  A ok = static_cast<A>(3);          // OK: within the range, although equal to no enumerator
  A a  = static_cast<A>(3 + argc);   // UB: 4 is out of range
  std::printf("%d %d\n", (int)ok, (int)a);
}
```

For an enumeration without a fixed underlying type, its range of values ([[dcl.enum]]) is the range of the smallest bit-field that can hold all the enumerators, not the set of enumerators itself. The enumerators of `enum A { e1 = 1, e2 }` are 1 and 2, which need 2 bits, so the range is 0 to 3: `static_cast<A>(3)` is valid, and only `static_cast<A>(4)` is undefined behavior. Enumerations with a fixed underlying type (`enum class`, or `enum E : int`) do not have this problem; any value of the underlying type is fine.

At run time UBSan's `enum` check reports `load of value 4, which is not a valid value for type 'A'` at the read; it does not check the conversion itself. Constant evaluation rejects it at the conversion, with `integer value 4 is outside the valid range of values [0, 3] for the enumeration type 'A'`.

### F.3.9 Converting a derived class pointer that does not point to a valid object to a virtual base pointer {#conv.ptr.virtual.base}

`[ub:conv.ptr.virtual.base]` · main text [[conv.ptr#3]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct B { int b; };
struct D : virtual B {};

int main() {
  D ds[1];
  B* b = &ds[1];   // UB: &ds[1] is a past-the-end pointer and does not point to an object
  return b != nullptr;
}
```

Converting to a virtual base requires reading the virtual base offset recorded in the object, so the pointer must point to an object within its lifetime (or under construction or destruction). A past-the-end pointer does not point to an object.

At run time ASan reports `stack-buffer-overflow`: the conversion read the memory just after `ds`. This is one of the few pure conversion UB that ASan can find indirectly.

### F.3.13 dynamic_cast of a non-null pointer that does not point to a suitable object {#expr.dynamic.cast.pointer.lifetime}

`[ub:expr.dynamic.cast.pointer.lifetime]` · main text [[expr.dynamic.cast#7]]

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B* dp = dynamic_cast<B*>(bs + 1);   // UB: bs + 1 is a past-the-end pointer
}
```

The run-time check of `dynamic_cast` reads the object's dynamic type information, so the operand must point to an object of suitable type within its lifetime (or under construction or destruction).

Running it reports nothing and returns a non-null pointer. The reason is that a `dynamic_cast` to the same type needs no run-time check, and Clang returns the operand directly without reading memory at all. With a target type that requires a run-time check, it would read the memory past the end.

### F.3.14 dynamic_cast of a glvalue that does not refer to a suitable object {#expr.dynamic.cast.glvalue.lifetime}

`[ub:expr.dynamic.cast.glvalue.lifetime]` · main text [[expr.dynamic.cast#7]]

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B& dr = dynamic_cast<B&>(bs[1]);   // UB (bs[1] itself is already the UB of F.3.20)
}
```

This is the reference version of F.3.13.

### F.3.10 Converting a pointer to base member to a pointer to derived member when the derived class cannot contain the member {#conv.member.missing.member}

`[ub:conv.member.missing.member]` · main text [[conv.mem#2]]

```cpp ub
struct B {};
struct D1 : B { int d1; };
struct D2 : B {};

void f() {
  int (D1::*pd1) = &D1::d1;
  int (B::*pb) = static_cast<int (B::*)>(pd1);   // OK: see the conditions in F.3.19
  int (D2::*pd2) = pb;                           // UB: D2 does not contain d1
}
```

The implicit conversion of pointers to members goes from base to derived, the opposite of object pointers: a member of the base is necessarily a member of the derived class too. But if the original member is not in the derived class at all, for example because it is a member of another derived class that was first `static_cast` to the base and then converted back, the result is undefined behavior.

Running it reports nothing. Add a member to `D2` and read through `pd2`, and you get that member's value, because a pointer to member is just an offset in the implementation.

### F.3.19 static_cast of a pointer to derived member to a base unrelated to the original member {#expr.static.cast.does.not.contain.original.member}

`[ub:expr.static.cast.does.not.contain.original.member]` · main text [[expr.static.cast#11]]

```cpp ub
struct A { char c; };
struct B { int i; };
struct D : A, B {};

int main() {
  char D::*p1 = &D::c;                        // c is a member of A
  char B::*p2 = static_cast<char B::*>(p1);   // UB: B does not contain c and is unrelated to A by inheritance
}
```

Converting a pointer to member in the derived-to-base direction needs an explicit `static_cast`. The result is valid if B contains the original member, or B is a base or derived class of the class containing the original member. The valid step in the F.3.10 example is of the latter kind.

## Function calls and member access

### F.3.11 Calling a function through an expression of incompatible type {#expr.call.different.type}

`[ub:expr.call.different.type]` · main text [[expr.call#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

using f_int = int (*)(int);
int f1(float x) { std::printf("%f\n", x); return 10; }

int main() {
  return reinterpret_cast<f_int>(f1)(20);   // UB: the expression's function type differs from f1's definition
}
```

The function type of the call expression must be call-compatible ([[g:call-compatible]]) with the type of the called function's definition: the same type, or differing only by a function pointer conversion that drops `noexcept`. Calling after changing the function pointer's type with `reinterpret_cast` is undefined behavior, because parameters of different types may be passed in entirely different registers.

At compile time Clang gives a `-Wcast-function-type-mismatch` warning. At run time UBSan's `function` check reports `call to function f1(float) through pointer to incorrect function type 'int (*)(int)'`. The program then prints a floating-point number unrelated to 20: the `int` argument was placed in an integer register, while `f1` took its value from a floating-point register. Constant evaluation does not allow `reinterpret_cast` at all, so this kind of undefined behavior cannot appear in constant expressions.

### F.3.12 In E1.E2, the object E1 refers to is not similar to the type of E1 {#expr.ref.member.not.similar}

`[ub:expr.ref.member.not.similar]` · main text [[expr.ref#10]]

```cpp ub
struct A { int i; };
struct B { int j; };

A a;
int x = reinterpret_cast<B&>(a).j;   // UB: a is an A, not a B
```

Member access requires the left side of the dot to really be an object of that type. The example in the main text makes the point more clearly: for an object `d` of `struct D : A, B {}`, `static_cast<B&>(d).j` is valid because it really refers to the B subobject of `d`; `reinterpret_cast<B&>(d).j` is undefined behavior because it refers to the starting address of `d`, where the A subobject is.

Running it reports nothing. A and B have the same layout, and the value of `a.i` is read.

### F.3.26 The object expression of .* does not contain the member {#expr.mptr.oper.not.contain.member}

`[ub:expr.mptr.oper.not.contain.member]` · main text [[expr.mptr.oper#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct B {};
struct D : B { int x; };

int main() {
  B* b = new B;
  D* d = static_cast<D*>(b);   // already UB in itself (F.3.18)
  int D::*p = &D::x;
  (*d).*p = 1;                 // UB: the dynamic type B does not contain x
  delete b;
}
```

In `E1.*E2`, the result of E1 must be an object whose type is similar to that of E1, and whose most derived object contains the member that E2 refers to.

At run time ASan reports `heap-buffer-overflow`: the write went past a B object that is only 1 byte. Constant evaluation stops earlier, at the `static_cast`, with `cannot cast object of dynamic type 'B' to type 'D'`.

### F.3.27 The second operand of .* is a null member pointer {#expr.mptr.oper.member.func.null}

`[ub:expr.mptr.oper.member.func.null]` · main text [[expr.mptr.oper#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct S { int f() { return 1; } };

int main() {
  S cs;
  int (S::*pm)() = nullptr;
  return (cs.*pm)();   // UB: the second operand is a null member pointer value
}
```

The annex entry's name contains func, but the rule in the main text treats pointers to data members and pointers to member functions alike.

At run time ASan reports `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`: the program jumped to address 0. Constant evaluation rejects it with `subexpression not valid in a constant expression`.

## new and delete

### F.3.21 A non-allocating placement new yields a null pointer {#expr.new.non.allocating.null}

`[ub:expr.new.non.allocating.null]` · main text [[expr.new#22]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct A { int x; };

int main() {
  char* p = nullptr;
  A* a = new (p) A;   // UB: a non-allocating new yields a null pointer
  return a != nullptr;
}
```

The `operator new(std::size_t, void*)` that `new (p) T` calls allocates nothing and just returns `p` as is ([[new.delete.placement]]). This non-allocating form cannot return a null pointer, so passing a null pointer to placement new is undefined behavior.

The annex's first example writes an `operator new(std::size_t, void*)` that returns a null pointer. That function is defined in `<new>` and is not replaceable, so defining it yourself already violates the library's rules; only the annex's second example is used here.

At run time UBSan reports `constructor call on null pointer of type 'A'`.

### F.3.22 The operand of single-object delete does not come from single-object new {#expr.delete.mismatch}

`[ub:expr.delete.mismatch]` · main text [[expr.delete#2]]

```cpp ub
int main() {
  int* x = new int[10];
  delete x;   // UB: single-object delete, operand from array new
}
```

In a single-object `delete p`, `p` may only be a null pointer, a pointer from a non-array *new-expression*, or a pointer to a base class subobject of an object created that way.

!!! lawyer "The annex and the main text disagree"
    In the current draft, the main text [[expr.delete#2]] attaches `[ub:expr.delete.mismatch]` to the sentence about single-object delete and `[ub:expr.delete.array.mismatch]` to the sentence about array delete; in Annex F the summaries and examples of these two entries are exactly the other way round (F.3.22 describes using array delete on the result of single-object new). Both cases are undefined behavior, so the conclusion is unaffected, but cite the main text. This page gives examples following the main text's attachment.

At compile time Clang warns `'delete' applied to a pointer that was allocated with 'new[]'; did you mean 'delete[]'? [-Wmismatched-new-delete]`. At run time, with `ASAN_OPTIONS=alloc_dealloc_mismatch=1` set, ASan reports `alloc-dealloc-mismatch (operator new [] vs operator delete)`. Constant evaluation rejects it with `non-array delete used to delete pointer to array object of type 'int[10]'`.

### F.3.23 The operand of array delete does not come from array new {#expr.delete.array.mismatch}

`[ub:expr.delete.array.mismatch]` · main text [[expr.delete#2]]

```cpp ub
int main() {
  int* x = new int;
  delete[] x;   // UB: array delete, operand from single-object new
}
```

In `delete[] p`, `p` may only be a null pointer or a pointer from an array *new-expression* (whose allocation function is not a non-allocating form). It must be that very pointer; a pointer to one of the elements or to a base class subobject will not do.

At compile time Clang warns `'delete[]' applied to a pointer that was allocated with 'new'; did you mean 'delete'?`. At run time, with `alloc_dealloc_mismatch=1` set, ASan reports `alloc-dealloc-mismatch (operator new vs operator delete [])`. Constant evaluation rejects it with `array delete used to delete pointer to non-array object of type 'int'`.

### F.3.24 Deleting a derived object through a base class pointer without a virtual destructor {#expr.delete.dynamic.type.differ}

`[ub:expr.delete.dynamic.type.differ]` · main text [[expr.delete#3]]

```cpp ub
struct B { int a; };
struct D : B { int b; };

void f() {
  B* b = new D;
  delete b;   // UB: B has no virtual destructor
}
```

In a single-object delete, if the static type of the object being deleted is not similar to its dynamic type, and the selected deallocation function is not a destroying operator delete (which takes care of calling the destructor itself), then the static type must be a base class of the dynamic type and must have a virtual destructor; otherwise the behavior is undefined.

Running the single-inheritance version reports nothing: `B` happens to be at the start of `D`, so the right pointer is freed; only `~D` is not called. With multiple inheritance (`struct D : A0, B`, deleting a `B*`), ASan reports `attempting free on address which was not malloc()-ed`: what is passed to `operator delete` is the address of the B subobject, not the start of the allocation. Constant evaluation rejects it with `delete of object with dynamic type 'D' through pointer to base class type 'B' with non-virtual destructor`.

### F.3.25 Dynamic type not similar to static type in array delete {#expr.delete.dynamic.array.dynamic.type.differ}

`[ub:expr.delete.dynamic.array.dynamic.type.differ]` · main text [[expr.delete#3]]

```cpp ub
struct B { virtual ~B() = default; int x; };
struct D : B { int y; };

void f(int n) {
  D* dp = new D[n];
  delete[] dp;   // OK
  B* bp = new D[n];
  delete[] bp;   // UB: even though B has a virtual destructor
}
```

There is no polymorphic deletion of arrays: even if B has a virtual destructor, deleting with `delete[]` a `B*` that points to an array of `D` is undefined behavior. Destroying the elements one by one requires knowing the element size, and the implementation can only get it from the static type.

Running this kind of code reports nothing. In this example `sizeof(D)` and `sizeof(B)` are both 16 (the Itanium ABI puts `y` in B's tail padding), so the stride happens to be right. Replacing the derived class with a larger type (`sizeof` 32 on our machine) and running it, there is still no report at all. Not seeing a problem does not mean the code is correct.
