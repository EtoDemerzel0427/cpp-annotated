---
title: Terms and definitions
summary: "The standard's vocabulary, centered on a set of terms for what code leads to: ill-formed, IFNDR, undefined, unspecified, implementation-defined and erroneous behavior."
updated: 2026-10-18
---

!!! tldr
    - A compiler accepting code does not mean the code conforms: some errors the standard does not require the compiler to report, and some only show up at run time.
    - The standard judges at two levels: whether the program itself is valid (well-formed, ill-formed, IFNDR), and what guarantees a valid program has when it runs (implementation-defined, unspecified, erroneous, undefined).
    - Undefined behavior means the standard places no requirements on the result; compilers assume it does not happen and optimize accordingly. C++26's erroneous behavior has a defined result, and compilers may not make that assumption.
    - Core-language undefined behavior is not allowed in constant evaluation, so `constexpr` can catch it for you at compile time.
    - The signature of an ordinary function does not include the return type; the signature of a function template does. This decides whether you can overload, and what the symbol name is at link time.

Clause 3 is the standard's glossary. It holds 69 terms used across clauses, each with a stable name such as [[defns.undefined]]. Most of the core terms of C++ (*odr-use*, *glvalue* and so on) are not here; they are defined in place in the subclause that uses them, see [[topics/how-to-read-the-standard]].


## If the compiler accepts it, is the code correct?

<div class="compare" markdown="1">

```cpp error
void g(int n) {
  int a[n];  // error: VLA
  a[0] = 0;
}
```

```cpp run ub
#include <climits>
#include <cstdio>
int inc(int x) { return x + 1; }
int main() {
  // UB: signed overflow
  std::printf("%d\n", inc(INT_MAX));
}
```

</div>

The code on the left violates a language rule: an array bound must be a constant expression. Yet by default Clang 23 gives only a `-Wvla-cxx-extension` warning and generates object code anyway.

The code on the right violates no rule, and compiling it with `-Wall -Wextra -pedantic` gives no warning at all. But this call makes a signed integer overflow, and the standard places no requirements on this execution. In our tests it printed `-2147483648`; with `-fsanitize=undefined`, UBSan reports `signed integer overflow`.

So the compiler's reaction is only a hint. To decide whether a piece of code is correct you have to answer two questions: does the program itself follow the language rules? If it does, what does the standard guarantee at run time? Clause 3 gives a precise vocabulary for both questions.

## Level one: is the program valid

### Well-formed and ill-formed

A **well-formed program** ([[defns.well.formed]]) is a program constructed according to the syntax rules and semantic rules. A program that is not well-formed is an **ill-formed program** ([[defns.ill.formed]]).

Well-formedness is a property of the program text and has nothing to do with run-time input. The program on the right above is well-formed, even though some input makes it overflow.

Most syntax and semantic rules are diagnosable rules ([[intro.compliance#1]]). If a program violates any of them, the compiler must issue at least one **diagnostic message** ([[defns.diagnostic]]); see [[intro.compliance#2.3]].

### A warning counts as a diagnostic

The definition of diagnostic message is a single sentence: a message belonging to an implementation-defined subset of the implementation's output messages. The standard does not distinguish errors from warnings, nor does it require the compiler to reject the program after a diagnostic.

So Clang's handling of the VLA fully conforms: that warning is its diagnostic, and compiling as usual afterwards is an extension permitted by [[intro.compliance#11]]. With `-pedantic-errors`, the warning becomes an error.

The standard requires an implementation not to accept a program in only a few places; the most common are a failed `static_assert` and the `#error` directive ([[intro.compliance#2.4]], [[intro.compliance#2.5]]).

### Ill-formed, no diagnostic required (IFNDR)

Some rules carry the note "no diagnostic is required". A program that violates such a rule is just as ill-formed, but the compiler may accept it silently, and the standard places no requirements on the whole program (not just the place with the error) ([[intro.compliance#2.2]]). This situation is usually abbreviated **IFNDR** (ill-formed, no diagnostic required).

Why is no diagnostic required? Because these errors can often be detected only by seeing the whole program, or are undecidable in general. The most typical is the ODR (one-definition rule, [[basic.def.odr]]): the definitions of the same inline function in different translation units (TUs) must be identical, but the compiler sees only one TU at a time.

```cpp title="a.cpp"
inline int answer() { return 42; }
int from_a() { return answer(); }
```

```cpp title="b.cpp" ifndr
#include <cstdio>
inline int answer() { return 43; }   // IFNDR: differs from the definition in a.cpp, violates the ODR
int from_a();
int main() { std::printf("%d %d\n", from_a(), answer()); }
```

With Clang 23, compiling and linking these two files produces no diagnostic at all. At `-O0`, linking in the order `a.cpp b.cpp` prints `42 42` and the other order prints `43 43`; at `-O2` it prints `42 43`, because the call in `from_a` was inlined. None of these three results violates the standard, because the standard places no requirements on this program.

IFNDR is not a Clause 3 term; it is a phrase derived from [[intro.compliance]]. The current draft's informative annex [[ifndr]] (Annex G) lists all such rules.

### Conditionally-supported constructs

Some constructs have no reasonable implementation on some platforms, yet are very useful on mainstream ones, for example converting a function pointer to `void*`. The standard marks them **conditionally-supported** ([[defns.cond.supp]]): an implementation may decline to support them, but its documentation must list which ones it does not support.

```cpp
void f();
void* p = reinterpret_cast<void*>(&f);   // function pointer to object pointer: conditionally-supported
struct NT { NT(); NT(const NT&); ~NT(); };
void v(int, ...);
void call(NT x) { v(0, x); }             // passing a non-trivial class object to ...: conditionally-supported
```

If an implementation does not support a construct and the program uses it, the implementation must diagnose it ([[intro.compliance#2.3.3]]). So a conditionally-supported construct never quietly turns into undefined behavior: it is either supported or rejected. Clang 23 supports the first one, which POSIX `dlsym` relies on; for the second, Clang chooses not to support it and issues a diagnostic that is an error by default (`-Wnon-pod-varargs`). The rules are in [[expr.reinterpret.cast#8]] and [[expr.call]] respectively.

### Implementation limits

The abstract machine has unlimited resources; real compilers do not. **Implementation limits** ([[defns.impl.limits]]) are restrictions an implementation imposes on programs, such as template instantiation depth or nesting levels. A program that violates no rule must be accepted and executed correctly, unless it exceeds these limits ([[intro.compliance#2.1]]). Annex [[implimits]] gives some recommended minimums, and they are only recommendations.

## Level two: what a well-formed program is guaranteed at run time

Even a well-formed program need not have only one outcome at run time. The standard classifies run-time behavior into the following categories, from the strongest constraint on the result to the weakest.

### Implementation-defined behavior

```cpp run impl
#include <climits>
#include <cstdio>
int main() {
  char c = '\xff';
  std::printf("%d %d\n", c, CHAR_MIN);   // whether char is signed is implementation-defined
}
```

On Apple arm64 this prints `-1 -128`. On the same AArch64 architecture, the Linux ABI specifies that `char` is unsigned, and it would print `255 0` (Clang's `-funsigned-char` can simulate this).

**Implementation-defined behavior** ([[defns.impl.defined]]) is behavior, for a well-formed construct and correct data, that depends on the implementation and that each implementation documents. You can look it up and rely on it on one platform; the code just isn't portable. Common examples are `sizeof(int)`, the signedness of `char`, the meaning of `#pragma`, and the string returned by `std::type_info::name()`.

[[intro.abstract#2]] treats these behaviors as parameters of the abstract machine: each implementation fills in the parameters in its documentation and thereby gets its own instance of the abstract machine.

There are two related categories. A **property of the implementation** ([[defns.impl.prop]]) likewise depends on the implementation but need not be documented, for example padding bytes in class objects, usually decided by the ABI. **Locale-specific behavior** ([[defns.locale.specific]]) depends on local conventions of nationality, culture and language and must be documented, for example which characters count as letters in a non-"C" locale.

!!! history
    C++20 fixed several behaviors that used to be implementation-defined: signed integers use two's complement representation, right-shifting a negative number is an arithmetic shift, and conversion to a signed type takes the value modulo 2ⁿ. Signed integer overflow is still undefined behavior.

### Unspecified behavior

```cpp run unspecified
#include <cstdio>
int g = 0;
int a() { g += 1; return g; }
int b() { g *= 2; return g; }
void show(int x, int y) { std::printf("%d %d\n", x, y); }
int main() {
  show(a(), b());   // calling a first prints "1 2", calling b first prints "1 0"
}
```

The order of evaluation of function arguments is not specified ([[expr.call]]). Clang 23 calls `a` first and prints `1 2`; another compiler may call `b` first and print `1 0`.

**Unspecified behavior** ([[defns.unspecified]]), like implementation-defined behavior, applies to well-formed constructs and correct data, with the result depending on the implementation. The difference is that the implementation need not document it, nor be consistent: different optimization levels, or two calls in the same program, may make different choices.

The possible outcomes are usually delineated by the standard. The example above can print only `1 2` or `1 0`, nothing else. Whether two string literals `"abc"` are the same object is also unspecified ([[lex.string]]).

!!! pitfall "Indeterminately sequenced vs unsequenced"
    Arguments are indeterminately sequenced with respect to each other, so the result is merely unspecified. If two modifications of the same scalar are unsequenced, as in `i++ + i++`, that is undefined behavior.

### Undefined behavior

**Undefined behavior** (UB, [[defns.undefined]]) is behavior for which the standard imposes no requirements. Take this literally: the standard neither requires the implementation to do anything nor forbids it from doing anything. A note to the definition lists some common manifestations: ignoring the situation with unpredictable results, behaving in a manner characteristic of the environment, or terminating translation or execution. These are only examples.

UB has two sources. One is where the standard explicitly says "the behavior is undefined"; Annex [[ub]] (Annex F) collects all such statements in the core language. The other is where the standard simply gives no definition for a situation; this kind of UB is not collected anywhere.

Why does the standard tolerate UB? There are three main reasons.

1. Different hardware reacts differently to the same operation. Integer division by zero traps on x86 and yields 0 on AArch64. Specifying any one behavior would make other platforms pay for extra checks.
2. Compilers can assume UB does not happen, draw stronger conclusions, and optimize more.
3. Many errors (dangling pointers, data races) cannot be decided at compile time; requiring a diagnostic would amount to requiring run-time checks.

Point 2 has a direct consequence:

```cpp ub
int inc_checked(int x) {
  int y = x + 1;          // when x == INT_MAX: UB
  if (y < x) return -1;   // meant to check after overflow
  return y;
}
bool always(int x) { return x + 1 > x; }
```

At `-O2`, Clang 23 compiles `inc_checked` into a single add instruction and deletes the `if` entirely, because it could only be true if overflow happened, and the compiler assumes overflow does not happen. `always` simply returns 1.

UB is a property of a particular execution, not of the program. `int f(int* p) { return *p; }` is fine by itself; only an execution that calls it with a null pointer contains UB. [[intro.abstract]] describes the consequences of UB at exactly this level, one execution with one set of inputs, and uses observable checkpoints to limit the effect of UB on behavior that has already happened.

### UB in constant evaluation

The last sentence of the note in [[defns.undefined]] says that the evaluation of a constant expression never exhibits behavior explicitly specified as undefined in Clauses 4 through 15 (the core language). In other words, if compile-time evaluation runs into core-language UB, the expression is not a constant expression, and where a constant expression is required the compiler must reject it.

This makes `constexpr` a ready-made UB detector. Here is the same out-of-bounds read, executed at compile time and at run time:

<div class="compare" markdown="1">

```cpp error
constexpr int sum3(const int* a) {
  int s = 0;
  for (int i = 0; i <= 3; ++i)
    s += a[i];
  return s;
}
constexpr int arr[3] = {1, 2, 3};
// error: out-of-bounds read, not a constant expression
static_assert(sum3(arr) == 6);
```

```cpp run ub
#include <cstdio>
int sum3(const int* a) {
  int s = 0;
  for (int i = 0; i <= 3; ++i)
    s += a[i];  // UB: reads a[3]
  return s;
}
int arr[3] = {1, 2, 3};
int main() {
  std::printf("%d\n", sum3(arr));
}
```

</div>

On the left, Clang reports `read of dereferenced one-past-the-end pointer`. The right one, at `-O0` in our tests, prints `6` and looks perfectly normal; only with `-fsanitize=address` is a `global-buffer-overflow` reported.

This guarantee covers only the core language. For library UB, such as violating a library function's precondition, it is unspecified whether it makes the expression non-constant during constant evaluation ([[expr.const.core#4]]), because the compiler cannot necessarily see through the library's implementation.

### Erroneous behavior {{c++26}}

**Erroneous behavior** (EB, [[defns.erroneous]]) is well-defined behavior that implementations are recommended to diagnose. It is always the consequence of incorrect code; a correct program never exhibits it. As with UB, core-language erroneous behavior never occurs in constant evaluation.

In C++26 the main source of erroneous behavior is reading an uninitialized automatic variable ([[basic.indet]]):

```cpp eb
int f() {
  int x;          // uninitialized: the bytes of x have erroneous values
  return x + 1;   // erroneous behavior in C++26; UB in C++23
}
```

An **erroneous value** is a value chosen by the implementation, independent of the program state. Reading it yields that value. The implementation may issue a diagnostic here and terminate the program ([[intro.abstract#6]]), or continue execution, but it may not do anything at all as it could for UB.

The fundamental difference from UB is that the compiler may not assume erroneous behavior does not happen, so it cannot delete code paths on that basis. If you really need the old semantics, for example to avoid initializing a large buffer for performance, you can mark the variable `[[indeterminate]]` ([[dcl.attr.indet]]); reading it is then UB again.

!!! impl
    At the time of writing, Clang 23 does not yet implement the semantics of erroneous behavior. For `f` above it gives a `-Wuninitialized` warning, and at `-O2` compiles `f` to a single `ret` that returns whatever is left in the register, still treating it as UB; it also does not yet recognize `[[indeterminate]]`. Clang's and GCC's `-ftrivial-auto-var-init=zero` gets a similar effect: in our tests, with this option `f` always returns 1.

!!! history
    Erroneous behavior was introduced by [[P2795]]. The motivation is security: uninitialized reads are the root of a large class of information-leak vulnerabilities, but simply specifying zero-initialization would turn incorrect code into correct code, and tools could no longer report it. Erroneous behavior makes the result predictable while the standard still considers it an error.

### Runtime-undefined behavior

**Runtime-undefined behavior** ([[defns.undefined.runtime]]) is UB at run time; during constant evaluation it is up to the implementation, which may treat the expression as non-constant or as if it were not there ([[expr.const.core#3]]). Currently it is used only for `[[assume]]` ([[dcl.attr.assume]]).

```cpp error
constexpr int g(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int a = g(1);    // OK
constexpr int b = g(-1);   // error: Clang chooses to treat a failed assumption as non-constant
```

Clang 23 reports `assumption evaluated to false`. Another implementation may accept `b` and initialize it to -1, which also conforms, so the `error` here is Clang's choice.

Why not just call it UB? If it were ordinary UB, then by the rule in the previous section the compiler would have to check every assumption during constant evaluation. But an assumption's expression may be very expensive, or even be designed never to be evaluated.

## Comparison

| Category | Is the program valid | Requirements on the result | Compiler's obligation | Example |
|---|---|---|---|---|
| Ill-formed {{ill-formed}} | No | None | At least one diagnostic (a warning counts) | Type errors, VLAs |
| IFNDR {{ifndr}} | No | None on the whole program | None | ODR violations |
| Conditionally-supported | Yes, when supported | Usually implementation-defined | Must diagnose when unsupported | Function pointer to `void*` |
| Implementation-defined {{impl}} | Yes | The implementation picks one | Document it | `sizeof(int)`, signedness of `char` |
| Unspecified {{unspec}} | Yes | One of the outcomes the standard allows | None; may differ each time | Order of argument evaluation |
| Erroneous {{erroneous}} | Yes | A defined result | Diagnosis recommended; may terminate | Reading an uninitialized automatic variable |
| Runtime-undefined | Yes | None at run time | Its own choice in constant evaluation | A false `[[assume]]` |
| Undefined {{ub}} | Yes (UB belongs to an execution) | None | None; must reject core-language UB in constant evaluation | Signed overflow, out-of-bounds access |

## Telling them apart in practice

What the compiler can tell you is mostly about level one. Level two relies on tools, tests and reading the standard.

| Category | Compiler | Other means |
|---|---|---|
| Ill-formed | Error or warning; `-pedantic-errors` turns extension-related warnings into errors | Cross-check with another compiler |
| IFNDR | Usually silent | GCC's `-Wodr` with LTO finds some ODR violations; the rest relies on code review |
| Implementation-defined | Follows its own documentation | Read the compiler and ABI documentation; when relying on it, pin the assumption with `static_assert` |
| Unspecified | Not reported | Don't rely on observed results; test with several compilers and optimization levels |
| Erroneous | Warnings such as `-Wuninitialized` | `-ftrivial-auto-var-init`; MemorySanitizer |
| Undefined | Warnings for some | UBSan, ASan, TSan; put the logic in `constexpr` tests |

For a suspicious piece of code, decide in this order:

1. Does it violate a syntax or semantic rule? If so, check whether the rule says no diagnostic is required: if it does, it's IFNDR; otherwise it's ill-formed.
2. If it's valid, see what the standard says about the result of the operation. If it gives a single result, the behavior is defined.
3. If it requires the implementation to document it, it is implementation-defined; if it gives several possible outcomes without requiring documentation, it is unspecified.
4. If the standard says erroneous, it is erroneous behavior; if it says undefined, or says nothing at all, it is undefined behavior.

For more examples and causes see [[topics/undefined-behavior]].

## Vocabulary for types and objects

### Static type and dynamic type

```cpp run ok
#include <typeinfo>
#include <cstdio>
struct B { virtual ~B() = default; };
struct D : B { };
int main() {
  D d;
  B* p = &d;                                     // *p: static type B, dynamic type D
  std::printf("%d\n", typeid(*p) == typeid(D));  // 1: typeid looks at the dynamic type
  B b = *p;                                      // slicing: initialization looks only at the static type
  std::printf("%d\n", typeid(b) == typeid(B));   // 1
}
```

The **static type** ([[defns.static.type]]) is the type of an expression obtained by analyzing the program text alone; it does not change during execution.

The **dynamic type** ([[defns.dynamic.type]]) is meaningful only for a glvalue (an expression that designates an object, see [[basic.lval]]): it is the type of the most derived object the glvalue refers to. A prvalue does not designate an object, and its dynamic type is its static type ([[defns.dynamic.type.prvalue]]). The two differ only because of derived-to-base conversions.

Many rules build on this pair of concepts: virtual function calls dispatch on the dynamic type ([[class.virtual]]); when you `delete` an object whose static type differs from its dynamic type, the base class must have a virtual destructor ([[expr.delete]]); the strict aliasing rule ([[basic.lval]]) uses them as well.

### Access

To **access** ([[defns.access]]) is to read or modify the value of an object. A note narrows the scope a lot: only glvalues of scalar type can access objects. Reading a scalar is covered in [[conv.lval]]; modifying one in [[expr.assign]] and the increment and decrement operators.

```cpp ok
struct S { int a; double b; };
void f(S& s, S& t) {
  t = s;   // calls the copy assignment operator; the call itself is not an access
           // inside it, reading s.a, s.b and writing t.a, t.b are the four accesses
}
```

Copying a class object calls a constructor or an assignment operator, and such a call is not itself an access. The distinction matters, because the strict aliasing rule ([[basic.lval]]), data races ([[intro.races]]) and observable behavior ([[intro.abstract]]) are all stated in terms of access; restricting it to scalars is what makes the boundaries of these rules clear.

### Referenceable type

A **referenceable type** ([[defns.referenceable]]) is a type for which a reference can be created: an object type, a reference type, or a function type that has neither cv-qualifiers nor a ref-qualifier. The only non-referenceable types are `void` and function types like `int() const` that can appear only in member function declarations. Type traits use this term to specify edge cases:

```cpp ok
#include <type_traits>
template<class T> using LRef = std::add_lvalue_reference_t<T>;
static_assert(std::is_same_v<LRef<void>, void>);                // not referenceable: returned unchanged
static_assert(std::is_same_v<LRef<int() const>, int() const>);  // not referenceable: returned unchanged
static_assert(std::is_same_v<LRef<int()>, int(&)()>);           // referenceable
static_assert(std::is_same_v<LRef<int&&>, int&>);               // reference collapsing
```

## Signatures

Can two functions with the same name coexist? How does the linker tell them apart? Both questions rest on the **signature** ([[defns.signature]]). The signature determines name mangling, that is, the linker symbol the compiler generates for each function.

<div class="compare" markdown="1">

```cpp error
int  f(int);
long f(int);  // error: differs only in the return type
```

```cpp run ok
template<class T>
int f(T) { return 1; }   // #1
template<class T>
long f(T) { return 2; }  // #2: OK
int main() {
  int  (*p)(int) = &f<int>;  // #1
  long (*q)(int) = &f<int>;  // #2
  return p(0) + q(0);        // 3
}
```

</div>

The signature of an ordinary function is its name, parameter-type-list and enclosing namespace, without the return type, so the two declarations on the left conflict. The signature of a function template also includes the return type and the template-head, so #1 and #2 on the right are two different templates. Writing `f(0)` directly would be ambiguous, but you can select one through the target type.

Templates are specified this way because two specializations both written `f<int>` may come from different templates and must be different symbols at link time. Under the Itanium C++ ABI (used by GCC and Clang on Linux and macOS), the two specializations on the right are mangled as `_Z1fIiEiT_` and `_Z1fIiElT_`; the `i` and `l` in the middle are the return types `int` and `long`. The ordinary function `int f(int)` is mangled as `_Z1fi`, with no return type.

The signature of a member function also includes its cv-qualifiers and ref-qualifier, so you can overload on them:

```cpp ok
struct S {
  void g() &;
  void g() &&;     // OK: different ref-qualifiers
  void h() const;
  void h();        // OK: different cv-qualifiers
};
```

`S::h() const` is mangled as `_ZNK1S1hEv` (`K` means const), and `S::g() &` as `_ZNR1S1gEv` (`R` means `&`).

The standard defines signatures separately for nine kinds of entity, made up as follows:

| Entity | The signature includes |
|---|---|
| Function | Name, parameter-type-list, enclosing namespace |
| Function template | The above + return type, signature of the template-head, trailing *requires-clause* |
| Function template specialization | Signature of the template + template arguments |
| Member function | Name, parameter-type-list, class of which it is a member, cv-qualifiers, ref-qualifier, trailing *requires-clause* |
| Member function template | The above + return type, signature of the template-head |
| Member function template specialization | Signature of the member function template + template arguments |
| Non-template friend with a trailing *requires-clause* | Name, parameter-type-list, enclosing class, trailing *requires-clause* |
| Friend function template whose constraint involves enclosing template parameters | Name, parameter-type-list, return type, enclosing class, signature of the template-head, trailing *requires-clause* |
| Template-head | Template parameter list (without parameter names and default arguments), *requires-clause* |

The two friend entries became necessary only after C++20 introduced constraints: a constrained friend defined in a class template is a different function in each instantiation, so its signature must include the enclosing class; otherwise same-named friends in `A<int>` and `A<long>` would conflict ([[temp.friend]]).

!!! lawyer "Which rule to cite for overloading"
    To decide whether two declarations declare the same entity, and whether they can overload, today's standard uses the correspondence rules in [[basic.scope.scope]], rather than saying directly that the signatures are the same. The two largely agree; when you need a precise argument, cite [[basic.scope.scope]]. Signatures mainly serve linkage and the library specification.

## Arguments and parameters

The standard strictly distinguishes an **argument** (what is given at the call site) from a **parameter** (a name introduced at the declaration). Both words have different definitions depending on the context:

| Context | Argument | Parameter |
|---|---|---|
| Function call | An expression or *braced-init-list* inside the parentheses | An object or reference declared in a function declaration or a `catch` clause |
| Function-like macro | A comma-separated sequence of preprocessing tokens inside the parentheses | An identifier in the parentheses after the macro name |
| Template | A constant expression, type or *id-expression* inside the angle brackets | A member of the *template-parameter-list* |
| `throw` expression | The operand of `throw` | |

A macro argument is a sequence of tokens, not an expression, and only parentheses protect the commas inside it. So `FIRST(std::pair<int, int>{}, 1)` is split into three arguments, and Clang reports `too many arguments provided to function-like macro invocation`.

## Terms in the library clauses

The following terms appear mainly in the library specification. They come up again and again when you read cppreference or the library clauses.

### Related to constant expressions

- **Constant subexpression** ([[defns.const.subexpr]]): an expression whose evaluation as a subexpression of a constant expression does not prevent it from being a constant expression. The library specification uses it to say whether a call can be used at compile time.
- **Non-constant library call** ([[defns.nonconst.libcall]]): a library function call that makes the enclosing expression no longer a constant expression; see [[expr.const.core#2.35]].
- **Expression-equivalent** ([[defns.expression.equivalent]]): a set of expressions that have the same effects, and agree on whether they are potentially-throwing and whether they are constant subexpressions. It is used to specify customization point objects ([[customization.point.object]]) like `ranges::begin`: saying `ranges::begin(E)` is expression-equivalent to `E.begin()` also means their `noexcept`-ness and constexpr-ness agree.

### Algorithms

A **projection** ([[defns.projection]]) is a transformation an algorithm applies before inspecting an element's value. A **stable algorithm** ([[defns.stable]]) preserves the original order of elements; for sorting algorithms, that means the relative order of equivalent elements is unchanged ([[algorithm.stable]]).

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <utility>
#include <vector>
int main() {
  std::vector<std::pair<int, char>> v{{2,'a'},{1,'b'},{2,'c'},{1,'d'}};
  // projection: compare by first only
  std::ranges::stable_sort(v, {}, &std::pair<int, char>::first);
  for (auto [k, c] : v) std::printf("%d%c ", k, c);  // 1b 1d 2a 2c
}
```

### Object states

A **valid but unspecified state** ([[defns.valid]]) means the object's value is not specified, but its invariants hold and operations on it behave as specified for its type. Moved-from standard library objects are usually in this state ([[lib.types.movedfrom]]). You can call operations without preconditions; for those with preconditions, check first:

```cpp run ok
#include <string>
#include <utility>
int main() {
  std::string s = "hello, world, a fairly long string";
  std::string t = std::move(s);   // s is in a valid but unspecified state
  s.clear();                      // OK: clear has no preconditions
  s = "again";                    // OK: assignment has no preconditions
  return s.back() == 'n' ? 0 : 1; // OK: s is now known to be non-empty
}
```

The library descriptions also use these words: a **modifier function** is a member function that changes the state of an object, excluding constructors, assignment and destructors; an **observer function** only reads the state and is specified as a `const` member function; **move construction** and **move assignment** mean initializing or assigning from an rvalue of the same type; they describe only the form of the expression, regardless of which constructor is actually called.

### Functions the program may provide

| Term | Meaning | Example |
|---|---|---|
| Replacement function | The program may provide a definition that replaces the library's default version | Global `operator new` ([[new.delete]]) |
| Handler function | The program provides a definition and installs it through a library function | A function passed to `std::set_terminate` |
| Reserved function | Defined by the implementation; if the program provides a definition, the behavior is undefined | |

Replacement and handler functions both have **required behavior**: if the version the program provides does not satisfy it at run time, the behavior is undefined. What the implementation's own version does within the required range is called its **default behavior**; see [[structure.specifications]].

### Program-defined types

A **program-defined type** ([[defns.prog.def.type]]) is a class or enumeration type that is not part of the standard library and not defined by the implementation, including the closure types of lambdas in the program. A **program-defined specialization** is an explicit or partial specialization written by the program.

These two terms decide what a program may add to `std`: it may add specializations only of standard library templates that depend on at least one program-defined type ([[namespace.std]]). Specializing `std::hash<MyType>` is fine; specializing `std::hash<int>` is not.

### A total order on pointers

Comparing two pointers that do not point into the same array with the built-in `<` gives an unspecified result ([[expr.rel]]). The standard library additionally specifies an **implementation-defined strict total order over pointers** ([[defns.order.ptr]]), consistent with the partial order given by the built-in operators. Function objects such as `std::less<T*>` are guaranteed to use it ([[comparisons]]), so you can use them to sort arbitrary pointers or use pointers as `std::map` keys.

## Common misconceptions

!!! pitfall "Signed overflow is implementation-defined"
    It isn't. Since C++20 the representation of signed integers is fixed as two's complement, but arithmetic overflow is still UB ([[expr.pre#4]]). Unsigned arithmetic does not overflow; it wraps around modulo 2ⁿ.

!!! pitfall "UB means the program will crash"
    A crash is only one possible outcome. More often the program looks fine (like the `6` printed by the out-of-bounds read above), or the optimizer deletes your check on the assumption that UB does not happen.

!!! pitfall "IFNDR is only a link-time problem"
    IFNDR rules are all over the standard: the ODR, a template definition for which no valid instantiation is possible ([[temp.res]]), the same constraint having different satisfaction results at different points, and so on. Violate any of them, and the standard no longer has any requirements on the whole program.

## Questions

!!! question "Question 1"
    Is the following program well-formed in C++23? In C++26? Does its execution have undefined behavior?
    ```cpp
    int main() { int x; return x; }
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed in both versions: it violates no syntax or semantic rule, and well-formedness has nothing to do with run-time behavior.

The difference is in execution. In C++23, reading an indeterminate value is UB. In C++26, the bytes of an uninitialized automatic variable have erroneous values, and reading it is erroneous behavior: the implementation may diagnose and terminate, otherwise `main` returns the value the implementation chose. Only marking `x` `[[indeterminate]]` brings back UB.
</details>

!!! question "Question 2"
    Can `template<class T> int f(T);` and `template<class T> long f(T);` both be declared in the same namespace? What about `int g(int);` and `long g(int);`?

<details markdown="1">
<summary>Answer</summary>

The former can, the latter cannot. The signature of a function template includes the return type, so the two templates do not correspond ([[basic.scope.scope#4]]) and can coexist; a call like `f(0)` is ambiguous, though, and needs a target type to select one.

In the latter, the signature is only the name, parameter-type-list and namespace, so both declarations declare the same function, but with different types; this violates [[basic.link#11]] and must be diagnosed.
</details>

!!! question "Question 3"
    Which category does `+"abc" == +"abc"` fall into? What about without the two unary `+`? `sizeof(long)`? `reinterpret_cast<void*>(&main)`?

<details markdown="1">
<summary>Answer</summary>

- `+"abc" == +"abc"`: unspecified. Unary `+` makes the arrays decay to pointers, so the addresses are compared, and whether two string literals are the same object is unspecified ([[lex.string]]).
- `"abc" == "abc"`: ill-formed in the current draft; two operands of array type cannot be compared directly ([[diff.cpp23.expr]]; deprecated from C++20 to C++23). Clang 23 rejects it with `-std=c++2c`.
- `sizeof(long)`: implementation-defined.
- `reinterpret_cast<void*>(&main)`: ill-formed; a program shall not odr-use `main` ([[basic.start.main]]). With an ordinary function `&f` instead, it is conditionally-supported.
</details>

<details class="fine" markdown="1">
<summary>Remaining wording</summary>

¶1 Besides the terms in this clause, the definitions in ISO/IEC 2382 (information technology vocabulary) and ISO 80000-2 (mathematical signs) also apply, so *byte*, the interval notation `[a, b)` and so on are understood according to these two documents. They are listed in [[intro.refs]].

¶2 gives the addresses of the ISO and IEC online terminology databases; this is standard boilerplate for ISO documents and has nothing to do with C++.

When the same English word has different definitions in different contexts, the context is marked with ⟨⟩, as in *block* ⟨execution⟩ and *block* ⟨statement⟩. ISO requires that a definition can directly replace the term in the text, so definitions are all written as noun phrases without articles.

Some terms related to execution: *block* ⟨execution⟩ ([[defns.block]]): wait for some condition to be satisfied before continuing execution; a thread that is merely not scheduled is not blocked (see [[intro.progress]]). *block* ⟨statement⟩ is a compound statement ([[stmt.block]]). *deadlock*: each thread is blocked waiting for a condition that only other threads can satisfy. *unblock*: satisfy the condition a blocked thread is waiting for. *constant evaluation* ([[defns.const.eval]]): evaluation performed as part of evaluating a core constant expression.

Characters and the C library: *C standard library*: the library described in Clause 7 of ISO/IEC 9899:2024, which, with the qualifications noted in [[diff.library]] and elsewhere, is a subset of the C++ standard library. *character* ⟨library⟩: an object that, when treated sequentially, can represent text; not limited to the `char` family, so the `MyChar` of `std::basic_string<MyChar>` counts too. *character container type*: a type that represents a character, a template parameter of templates like `char_traits` and `basic_string`. *NTCTS*: a sequence of characters terminated by `charT()`, that is, a C-style string over any character type.

Library organization: *component*: a group of library entities directly related as members, parameters or return types, such as the string component. *traits class*: a class that encapsulates a set of types and functions for templates to manipulate the types they are instantiated with, such as `char_traits` and `iterator_traits`.

The seven terms specific to the regular expressions library ([[re]]) follow the concepts of ECMAScript and POSIX: *collating element*, *finite state machine*, *format specifier* (such as `$1`), *matched*, *primary equivalence class*, *regular expression*, *sub-expression*.

In C++14 and earlier, terms and definitions were subclause 1.3 of Clause 1; C++17 moved them to Clause 3 following the structure of ISO documents, and the stable name `[intro.defs]` did not change. Runtime-undefined behavior, Annex F and Annex G were added after C++23.

</details>
