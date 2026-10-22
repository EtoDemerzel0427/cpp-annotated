---
title: Exam 2 · Initialization, value categories and references
summary: 25 questions on where default-, value- and zero-initialization part ways, list-initialization and narrowing, how the aggregate rules changed between standards, copy- versus direct-initialization, reference binding, value categories and decltype, guaranteed copy elision, implicit move, and C++26 erroneous behavior and static initialization.
tags: initialization, list-initialization, aggregates, reference binding, value categories, decltype, copy elision, erroneous behavior, exam
updated: 2026-10-20
---

!!! tldr
    - Scope: the forms of initialization in [[dcl.init]], [[dcl.init.list]] and narrowing, [[dcl.init.aggr]], [[dcl.init.ref]], [[basic.lval]] and [[dcl.type.decltype]], `auto` deduction, [[class.copy.elision]] and implicit move, erroneous values in [[basic.indet]], and [[basic.start.static]].
    - Object lifetime and temporaries, name lookup and overload resolution, templates, and constant evaluation have exams of their own; this one cites them only where a verdict needs them.
    - 25 questions: 15 verdict, 7 multiple choice, 3 open-ended, roughly increasing in difficulty. Suggested time: 90 minutes.
    - For verdict questions, answer with the most severe property of the whole program. All question code has been tested with Clang 23 (`-std=c++2c`); where the compiler disagrees with the draft, the explanation says so.

## 1. Default-, value- and zero-initialization

<div class="quiz" data-kind="verdict" data-answer="eb" markdown="1">

Judge this program.

```cpp run
struct A { A() = default; int i; };
struct B { B(); int i; };
B::B() = default;

int main() {
  A a{};
  B b{};
  return a.i + b.i;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: erroneous behavior.**

1. `A` and `B` both have user-declared constructors, so since C++20 neither is an aggregate ([[dcl.init.aggr#1.1]]). Empty braces initializing a class with a default constructor perform value-initialization ([[dcl.init.list#3.5]]).
2. Value-initialization depends on whether the selected default constructor is user-provided: if it is not, the object is zero-initialized first and then default-initialized ([[dcl.init#8.1]]). A function is user-provided if it is not explicitly defaulted or deleted on its first declaration ([[dcl.fct.def.default#5]]). `A()` is defaulted inside the class and is not user-provided, so `a.i` is 0.
3. `B()` is only declared inside the class and defaulted outside it, so it is user-provided. `b` is only default-initialized, which means calling `B()`. `B()` has no mem-initializer for `i`, so `i` is default-initialized ([[class.base.init#9.3]]), which for `int` does nothing ([[dcl.init#6.4]]).
4. `b` has automatic storage duration, and bytes that are not initialized hold erroneous values ([[basic.indet#1.2]]). Reading `b.i` in the `return` produces an erroneous value, and the behavior is erroneous ([[basic.indet#2]]). In C++23 and earlier this was undefined behavior.

Clang 23 does not yet implement the semantics of erroneous behavior. At run time it returns leftover stack contents whose value varies with compiler options, and gives no diagnostic.

<div class="compare" markdown="1">

```cpp ok
struct B { B() = default; int i; };
int main() {
  B b{};
  return b.i;   // 0
}
```

```cpp eb
struct B { B(); int i; };
B::B() = default;
int main() {
  B b{};
  return b.i;   // erroneous value
}
```

</div>

For a walkthrough, see the section of [[topics/initialization]] on why an out-of-class `= default` is user-provided.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program. `s` has static storage duration.

```cpp run
struct S {
  S() = default;
  int i;
};

const S s;

int main() { return s.i; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. `s` has no initializer, so it is default-initialized ([[dcl.init#11]]).
2. If a program calls for the default-initialization of an object of const-qualified type, the type must be const-default-constructible ([[dcl.init#7]]).
3. Checking `S` item by item: the `S()` called by default-initialization is not user-provided, so [[dcl.init#7.3]] is not satisfied; `S`'s member `i` has no default member initializer and `int` itself is not const-default-constructible, so [[dcl.init#7.4.1]] is not satisfied. So `S` is not const-default-constructible, and the program is ill-formed.

The tempting argument for well-formed is that `s` has static storage duration, is zero-initialized first, and `s.i` has the definite value 0. But [[dcl.init#7]] constrains the requirement for default-initialization itself; it looks neither at the storage duration nor at the result after zero-initialization. The intent: a const object cannot be assigned later, and if its construction initializes nothing, its value can only come from zero-initialization or be indeterminate, so the standard asks the programmer to say explicitly what they mean.

Clang's diagnostic is `default initialization of an object of const type 'const S' without a user-provided default constructor`.

<div class="compare" markdown="1">

```cpp ok
struct S {
  S() = default;
  int i = 0;    // has a default member initializer
};
const S s;
```

```cpp ok
struct S {
  S() = default;
  int i;
};
const S s{};    // value-initialization, not default-initialization
```

</div>

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

Of the four objects in `f`, which one's member `n` is not guaranteed to be 0?

```cpp run
struct M { M() { } };
struct S1 { M m; int n; };
struct S2 { M m; int n; S2() = default; };
struct S3 { M m; int n; S3(); };
S3::S3() = default;

void f() {
  S1 a{};               // A: a.n
  S2 b{};               // B: b.n
  S3* p = new S3();     // C: p->n
  thread_local S3 t;    // D: t.n
  delete p;
}
```

- A. `a.n`
- B. `b.n`
- C. `p->n`
- D. `t.n`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

- A: `S1` is an aggregate, and `{}` performs aggregate initialization. `n` is not explicitly initialized and has no default member initializer, so it is copy-initialized from an empty initializer list ([[dcl.init.aggr#6.2]]) and becomes 0.
- B: `S2` has a user-declared constructor, so it is not an aggregate, and `b{}` performs value-initialization ([[dcl.init.list#3.5]]). `S2()` is defaulted inside the class and is not user-provided, so the object is zero-initialized first ([[dcl.init#8.1]]). Member `m`'s constructor is user-provided, which makes `S2()` non-trivial, but zero-initialization depends only on whether `S2()` itself is user-provided, not on whether it is trivial.
- C: the `()` in `new S3()` is interpreted by the rules of direct-initialization ([[expr.new#24.2]]), which means value-initialization ([[dcl.init#15.4]]). `S3()` is defaulted outside the class and is user-provided, so there is no zero-initialization; only `S3()` is called, and `n` is not initialized. The bytes of an object with dynamic storage duration have indeterminate values ([[basic.indet#1.1]]), and reading `p->n` is undefined behavior.
- D: `t` has thread storage duration and is not constant-initialized, so it is zero-initialized first ([[basic.start.static#2]]). The subsequent dynamic initialization calls `S3()`, which does not touch `n`, so `n` remains 0.

The distractor is D: `thread_local S3 t;` uses default-initialization and looks as if it does nothing, just like C. The difference is that objects with static or thread storage duration are always zeroed before any dynamic initialization.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
struct Timer { };
struct Clock {
  Clock(Timer) { }
  int now() const { return 0; }
};

int main() {
  Clock c(Timer());
  return c.now();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. `Clock c(Timer());` can be read as initializing an object `c` with the functional-notation conversion `Timer()`, or as declaring a function `c` whose parameter is unnamed and of type "function with no parameters returning `Timer`". Anything that can be interpreted as a declaration is a declaration ([[dcl.ambig.res#1]]).
2. A parameter of function type is adjusted to pointer to function ([[dcl.fct#5]]), so `c` has type `Clock(Timer (*)())`.
3. `c.now()` performs member access on a function, which is ill-formed. Clang first warns with `-Wvexing-parse` and then reports `member reference base type 'Clock (Timer (*)())' is not a structure or union`.

The declaration in step 1 is itself well-formed; it declares a function. The error is on the next line. The fix is to make it impossible to read as a declaration:

<div class="compare" markdown="1">

```cpp ok
Clock c{Timer()};     // list-initialization
Clock d((Timer()));   // extra parentheses around the argument
Clock e = Timer();    // copy-initialization
```

```cpp error
Clock c(Timer());     // function declaration
int n = c.now();      // error: c is a function
```

</div>

</details>
</div>

## 2. List-initialization, narrowing and aggregates

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Which of these four namespace-scope declarations is ill-formed? Assume `float` is the IEEE 754 single-precision type.

```cpp run
const int big = 255;
constexpr long long p = 1LL << 40;

unsigned char c{big};   // A
float f{p};             // B
float g{0.1};           // C
bool b = {nullptr};     // D
```

- A. `unsigned char c{big};`
- B. `float f{p};`
- C. `float g{0.1};`
- D. `bool b = {nullptr};`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

- A: `int` to `unsigned char` is normally narrowing, but the source is a constant expression whose value, 255, fits in the target type after integral promotions, which is an exception ([[dcl.init.list#7.4.2]]).
- B: integer to floating-point is normally narrowing, but the source is a constant expression and 2⁴⁰ can be represented exactly by `float` and converts back to the original value, which is an exception ([[dcl.init.list#7.3]]). With `(1LL << 53) + 1` it no longer fits, and Clang reports `constant expression evaluates to 9007199254740993 which cannot be narrowed to type 'float'`.
- C: `double` to `float` is a conversion to a floating-point type of lower conversion rank, but when the result is a constant expression and the value is finite and does not overflow, it is not narrowing ([[dcl.init.list#7.2]]). It does not matter that 0.1 cannot be represented exactly as `float`; this exception only requires no overflow.
- D: there is no narrowing here. `= {nullptr}` is copy-list-initialization with a single element, handled as copy-initialization ([[dcl.init.list#3.9]]). The special rule from `std::nullptr_t` to `bool` exists only for direct-initialization ([[dcl.init#15.8]]); copy-initialization uses standard conversions ([[dcl.init#15.9]]), and boolean conversions do not include `std::nullptr_t` as a source type ([[conv.bool#1]]). So it is ill-formed.

Changing D to `bool b{nullptr};` makes it well-formed, with `b` being `false`: direct-list-initialization is handled as direct-initialization and lands exactly on [[dcl.init#15.8]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

What does this program print? (Each `puts` prints one line; the lines are listed in order.)

```cpp run
#include <cstdio>
#include <initializer_list>

struct X {
  X() { }
  X(const X&) { std::puts("copy"); }
  X(std::initializer_list<X>) { std::puts("list"); }
};

int main() {
  X a;
  X b{a};
  X c(a);
}
```

- A. `copy` `copy`
- B. `list` `copy`
- C. `copy` `list` `copy`
- D. `list` `list`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

1. `X b{a};`: `X` is not an aggregate, so the rule in [[dcl.init.list#3.2]] (copying directly from a single element of the same type) does not apply. We reach [[dcl.init.list#3.7]], and constructors are selected in two phases per [[over.match.list#1]]. The first phase considers only initializer-list constructors, with the whole `{a}` as a single argument. `{a}` can be converted to `std::initializer_list<X>`, so the first phase succeeds and the copy constructor is never even compared.
2. To construct the `std::initializer_list<X>`, the implementation creates a backing array of type `const X[1]` whose element is copy-initialized from `a` ([[dcl.init.list#5]]); this prints `copy`. Then the list constructor body runs and prints `list`.
3. `X c(a);` is direct-initialization, not list-initialization, and selects among all constructors per [[over.match.ctor#1]]. `a` cannot be converted to `std::initializer_list<X>`, so only the copy constructor is viable, and it prints `copy`.

B is the most common wrong answer: it remembers that the list constructor wins but forgets that the element of the backing array must itself be copied.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
#include <cstdio>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{{"a", "b"}};
  std::printf("%zu\n", v.size());
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

1. The outer `{…}` has a single element, `{"a", "b"}`. `vector` has an initializer-list constructor, which the first phase tries ([[over.match.list#1]]): `{"a", "b"}` must be converted to `std::string`.
2. List-initializing a `std::string` from `{"a", "b"}`: the `initializer_list<char>` constructor is not viable (a string literal cannot be converted to `char`), so the second phase selects among all constructors, and the only viable one is the iterator-range constructor `basic_string(InputIterator, InputIterator)`, with `InputIterator` deduced as `const char*` ([[string.cons#20]]).
3. So the first phase succeeds, and `v` has a single element constructed from the range `["a", "b")`. The two literals are two distinct array objects; incrementing a pointer into one never reaches the other, so the range is invalid. Applying a library function to an invalid range has undefined results ([[iterator.requirements.general#12]]).

In our tests AddressSanitizer reports `global-buffer-overflow`: `basic_string` reads from `"a"` for a length of `"b" - "a"`.

The tempting answer is well-formed, on the reasoning that "the outer braces call `vector(initializer_list<string>)` and the inner ones are two strings". In fact the inner braces are a single element, and the two literals are constructor arguments for that element.

<div class="compare" markdown="1">

```cpp ok
std::vector<std::string> v{"a", "b"};      // 2 elements
std::vector<std::string> w{{"a"}, {"b"}};  // 2 elements
```

```cpp ub
std::vector<std::string> v{{"a", "b"}};    // 1 element, invalid range
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program against the current draft.

```cpp run
struct A {
  A() = delete;
  int x;
};

A a{};

int main() { return a.x; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. `A() = delete` is a user-declared constructor, so `A` is not an aggregate ([[dcl.init.aggr#1.1]]).
2. `a{}` is an empty list and `A` has a default constructor (a deleted one still counts as declared), so value-initialization is performed ([[dcl.init.list#3.5]]). Value-initialization first decides whether to zero-initialize, then default-initializes, which calls the selected `A()` ([[dcl.init#8.1]], [[dcl.init#6.1]]).
3. Calling a deleted function is ill-formed ([[dcl.fct.def.delete#2]]).

In C++17 this program was well-formed: the aggregate definition then only excluded user-provided, explicit and inherited constructors; `= delete` is not user-provided, so `A` was still an aggregate, and `a{}` performed aggregate initialization without calling any constructor. That let a class with a deleted default constructor still be created with `{}`. C++20's [[P1008R1]] changed the condition to "no user-declared constructors", closing the gap. Compiled with `-std=c++17`, Clang accepts this program.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
struct A {
  int a;
  const int& r;
};

int main() {
  A x(1.5, 2);
  return x.a + x.r;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

1. `A` is an aggregate, no constructor is viable, and the initializer is a parenthesized expression-list, so the parenthesized aggregate initialization introduced in C++20 applies: each element is copy-initialized from the corresponding expression in turn ([[dcl.init#15.6.2.2]]).
2. The parenthesized form allows narrowing; `1.5` converts to `int` as 1 without an error (note 7 in [[dcl.init#15.6.2.2]]).
3. `r` binds to a temporary materialized from `2`. When an aggregate is initialized from a parenthesized expression-list, a temporary bound to a reference element persists only until the end of the full-expression containing the expression-list ([[class.temporary#6.11]]). By the time the next line reads `x.r`, the temporary has been destroyed, and accessing it is undefined behavior ([[basic.life]]).

In our tests Clang gives a `-Wdangling` warning and AddressSanitizer reports `stack-use-after-scope`.

Switch to braces and both things change: the narrowing makes the program ill-formed, and the temporary bound to the reference member has its lifetime extended.

<div class="compare" markdown="1">

```cpp ok
A x{1, 2};      // the temporary's lifetime is extended until x ends
int n = x.r;    // 2
```

```cpp error
A y{1.5, 2};    // error: narrowing
```

</div>

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

According to the current draft, which line is ill-formed?

```cpp
struct A { int x; int y; };
struct B : A { int z; };

A a1{.x = 1};               // A
B b1{.x = 1, .z = 3};       // B
B b2{A{1, 2}, .z = 3};      // C
A a2{1, .y = 2};            // D
```

- A. `A a1{.x = 1};`
- B. `B b1{.x = 1, .z = 3};`
- C. `B b2{A{1, 2}, .z = 3};`
- D. `A a2{1, .y = 2};`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

The current draft's grammar lets a designated-initializer-list start with some ordinary clauses followed by designated clauses (*designated-initializer-list* in [[dcl.init]]), and lets designators name members of aggregate base classes. The constraints are concentrated in [[dcl.init.aggr#4.1]]:

- Each designator is looked up in the class `C` and must find a unique non-static data member, and the type of the subobject containing it must be an aggregate base of `C` (`C` itself, or recursively one of its direct bases).
- Each ordinary clause at the front of the list must correspond to a direct base class subobject of `C`.

Applying this line by line:

- A: only `x` is designated; `y` is initialized from an empty list to 0 ([[dcl.init.aggr#6.2]]). Well-formed.
- B: `.x` finds a member of base `A`, and `A` is an aggregate base of `B`; the explicitly initialized elements are the base `A` and `B::z`, and the base `A` is in turn initialized from `{.x = 1}` ([[dcl.init.aggr#5.2.2]]). Well-formed.
- C: the ordinary clause `A{1, 2}` corresponds to the direct base `A`, and `.z` designates the class's own member. Well-formed.
- D: the ordinary clause `1` corresponds to the data member `x`, not to a base class subobject, violating [[dcl.init.aggr#4.1]]. The draft's example at the same place, `A{1, .a2=2}`, is marked as an error.

The ordering rule for designated initialization still holds: designators must appear in member declaration order ([[dcl.init.list#3.1]]).

Relaxing designators for bases comes from [[P2287R5]], wording newer than C++23. Clang 23 does not implement it yet: B is rejected (`field designator 'x' does not refer to any field in type 'B'`), while C and D only get the `-Wc99-designator` extension warning. So on Clang, B fails and D passes, exactly the opposite of the draft. For how to choose in practice, see [[patterns/named-parameters]].

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

For C++17 and for the current draft separately, decide whether each of the four variable definitions is well-formed, and explain why.

```cpp
struct P { explicit P() = default; int i; };
struct Q { private: Q() = default; public: int i; };
struct R { int i; int j; };

P p1{};
P p2 = {};
Q q1{};
R r1(1, 2);
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer:**

| Definition | C++17 | Current draft |
|---|---|---|
| `P p1{};` | well-formed | well-formed |
| `P p2 = {};` | ill-formed | ill-formed |
| `Q q1{};` | well-formed | ill-formed |
| `R r1(1, 2);` | ill-formed | well-formed |

**`P`**. In C++17 an aggregate could not have explicit constructors; in the current draft an aggregate cannot have any user-declared constructors ([[dcl.init.aggr#1.1]]). So `P` is not an aggregate in either version, and the conclusions are the same.

- `p1{}` is direct-list-initialization with an empty list: value-initialization ([[dcl.init.list#3.5]]). Default-initialization selects among all constructors ([[over.match.ctor#1]]), and selecting the explicit `P()` is fine. `P()` is not user-provided, so `i` is zeroed first.
- `p2 = {}` is copy-list-initialization. It also value-initializes, but the last sentence of [[over.match.ctor#1]] says that for default-initialization in the context of copy-list-initialization, if an explicit constructor is chosen, the initialization is ill-formed. The rule comes from [[CWG1518]], and Clang applies it in C++17 mode as well.

**`Q`**. In C++17 `Q` is an aggregate: a defaulted private constructor is neither user-provided nor explicit, and the aggregate definition did not look at constructor access at the time. `q1{}` performs aggregate initialization and calls no constructor, so the private constructor might as well not exist. In the current draft `Q` has a user-declared constructor and is not an aggregate; `q1{}` value-initializes, calls the private `Q()`, and fails the access check ([[class.access]]). The rule change came from [[P1008R1]], and this kind of access-control bypass in `Q` was one of its motivations.

**`R`**. In C++17 only braces could perform aggregate initialization; `R` has no constructor taking two `int`s, so `r1(1, 2)` is ill-formed. Since C++20, when no constructor is viable, the target is an aggregate and the initializer is a parenthesized expression-list, the elements are copy-initialized one by one ([[dcl.init#15.6.2.2]], [[P0960R3]]).

Every cell above has been checked with Clang 23 using `-std=c++17` and `-std=c++2c`.

</details>
</div>

## 3. Copy-initialization, direct-initialization and reference binding

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this translation unit (assume both constructors are defined elsewhere).

```cpp
struct E {
  explicit E(int);
  E(long);
};

E a = 1;
E b = {1};
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.** The error is in `b`.

1. `E a = 1;` copy-initializes a class object from an `int`. The source and target types differ, so [[dcl.init#15.6.3]] applies and candidates are enumerated per [[over.match.copy#1]]: only non-explicit constructors are candidates. `E(int)` does not take part at all, `E(long)` is selected, and it is well-formed.
2. `E b = {1};` is copy-list-initialization, handled by [[dcl.init.list#3.7]] and [[over.match.list#1]]. `E` has no initializer-list constructor, so in the second phase the candidates are all constructors, including explicit ones. `1` to `int` is an exact match and `1` to `long` is an integral conversion, so by rank `E(int)` wins ([[over.ics.rank#4]]).
3. Once it is selected, [[over.match.list#1]] says that if copy-list-initialization chooses an explicit constructor, the initialization is ill-formed. It does not fall back to `E(long)`.

This is the difference that note 1 of [[over.match.list]] points out: ordinary copy-initialization excludes explicit constructors from the candidates, whereas copy-list-initialization lets them take part in overload resolution and only errors out if one is finally chosen. Clang's diagnostic is `chosen constructor is explicit in copy-initialization`.

<div class="compare" markdown="1">

```cpp ok
E a = 1;      // only non-explicit considered: E(long)
E c{1};       // direct-list-initialization: E(int)
E d = {1L};   // E(long) is an exact match
```

```cpp error
E b = {1};    // explicit E(int) chosen: error
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
struct Flag {
  explicit operator bool() const { return true; }
};

int main() {
  Flag f;
  bool b1(f);
  bool b2{f};
  int n = f ? 1 : 0;
  return b1 + b2 + n;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.** The program returns 3.

1. `bool b1(f);` is direct-initialization of a non-class target from a class-type source, so conversion functions are considered per [[dcl.init#15.7]], with candidates given by [[over.match.conv#1]]: for direct-initialization, explicit conversion functions whose return type can be converted to `bool` with a qualification conversion are also candidates. `explicit operator bool` is selected.
2. `bool b2{f};` is direct-list-initialization with a single element, handled as direct-initialization ([[dcl.init.list#3.9]]), so it also lands on [[dcl.init#15.7]] and may use the explicit conversion function. This is a user-defined conversion, not narrowing.
3. The first operand of `f ? 1 : 0` is contextually converted to `bool` ([[expr.cond#1]]), which is defined as `bool t(f);` being well-formed ([[conv.general#4]]), which is exactly step 1.

The tempting argument for ill-formed is that explicit conversion functions can only be used in contexts such as `if`, `!` and `&&`. In fact they are usable in any direct-initialization; contextual conversion merely borrows the form of direct-initialization.

<div class="compare" markdown="1">

```cpp ok
bool b1(f);
bool b2{f};
bool b3 = static_cast<bool>(f);
```

```cpp error
bool b4 = f;      // copy-initialization: no usable conversion
bool b5 = {f};    // copy-list-initialization: same
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
int main() {
  int i = 1;
  long&& r = i;
  r = 5;
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.** The program returns 1.

Walk through the branches of [[dcl.init.ref#5]] one at a time:

1. [[dcl.init.ref#5.1]] and [[dcl.init.ref#5.2]] apply only to lvalue references; skip them.
2. [[dcl.init.ref#5.3]] requires the initializer to be an rvalue (or a function lvalue), or of a class type convertible to an rvalue. `i` is an `int` lvalue, which satisfies none of these.
3. [[dcl.init.ref#5.4]] requires `long` not to be reference-related to `int`. `long` is reference-related to `int` if `long` is similar to `int` or is a base class of `int` ([[dcl.init.ref#4]]); neither holds, so the condition is met.
4. [[dcl.init.ref#5.4.2]]: `i` is implicitly converted to a prvalue of type `long`, which is materialized, and `r` binds to that temporary. The temporary's lifetime is extended to that of `r` ([[class.temporary#6]]).

`r = 5` modifies the temporary; `i` is still 1.

The tempting argument for ill-formed is that an rvalue reference cannot bind to an lvalue. That rule really only targets reference-related types: [[dcl.init.ref#5.4]] begins by requiring the types not to be reference-related, so `int&& r = i;` is ill-formed, whereas `long&&` is not bound to `i` at all but to a newly converted object. Likewise, `const long& cr = i;` also binds to a temporary, and later changes to `i` are not reflected in `cr`.

<div class="compare" markdown="1">

```cpp ok
int i = 1;
long&& r = i;          // binds to a temporary long
const long& cr = i;    // also a temporary
```

```cpp error
int i = 1;
int&& r = i;           // reference-related, and i is an lvalue
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
#include <utility>

struct S { int bf : 4; };

int main() {
  S s{3};
  int&& r = std::move(s.bf);
  return r;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. The parameter of `std::move` is a forwarding reference `T&&`. The argument `s.bf` is an `int` lvalue, so `T` is deduced as `int&` and the parameter type collapses to `int&`.
2. Initializing an `int&` from a bit-field: [[dcl.init.ref#5.1.1]] explicitly excludes bit-fields, and [[dcl.init.ref#5.2]] says that in the remaining cases a non-const lvalue reference makes the program ill-formed. [[class.bit#3]] also says directly that a non-const reference shall not bind to a bit-field.
3. Forming an implicit conversion sequence does not consider whether the argument is a bit-field (note 1 in [[over.best.ics.general#2]]), so overload resolution still selects `std::move`; the error occurs when the parameter is actually bound.

Clang reports `non-const reference cannot bind to bit-field 'bf'`, pointing at the call to `std::move`.

It is tempting to call this well-formed because `std::move(x)` is habitually treated as a cast usable on any lvalue. It is a function call with a reference parameter, and a bit-field has no address for a reference to point to. When you need an rvalue, extract the bit-field's value first:

```cpp ok
int v = s.bf;
int&& r = std::move(v);
```

</details>
</div>

## 4. Value categories, decltype and auto

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

Which of the four `static_assert`s below fails?

```cpp
#include <type_traits>
#include <utility>

struct S { int m; };
S make();
void fn();

void test(bool b, int x, int y) {
  static_assert(std::is_same_v<decltype((make().m)), int&&>);              // A
  static_assert(std::is_same_v<decltype((std::move(fn))), void(&&)()>);    // B
  static_assert(std::is_same_v<decltype((b ? x : std::move(y))), int>);    // C
  static_assert(std::is_same_v<decltype(("abc")), const char(&)[4]>);      // D
}
```

- A. Assertion A (`make().m`)
- B. Assertion B (`std::move(fn)`)
- C. Assertion C (the conditional expression)
- D. Assertion D (the string literal)

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

All four operands are parenthesized, so none is an unparenthesized *id-expression* or member access, and `decltype` gives a type based on value category: `T&&` for an xvalue, `T&` for an lvalue, `T` for a prvalue ([[dcl.type.decltype#1.5]], [[dcl.type.decltype#1.6]], [[dcl.type.decltype#1.7]]).

- A: `make()` is a prvalue. Member access requires a glvalue left operand, so the prvalue is first materialized into an xvalue ([[basic.lval#7]]); when the left operand is not an lvalue, `E1.E2` is an xvalue ([[expr.ref#8.2]]). So it is `int&&`, and the assertion holds.
- B: `std::move(fn)` returns `void(&&)()`. A function call whose return type is an rvalue reference to function is an lvalue ([[expr.call#15]]). For function types, rvalue references are treated as lvalues whether named or not (note 3 in [[basic.lval#4]]). So `decltype` yields `void(&)()`, and the assertion fails.
- C: the second and third operands have the same type (`int`), but one is an lvalue and the other an xvalue. [[expr.cond#4]] attempts conversions only when the types differ and one is a class type, or when both are glvalues of the same value category whose types differ only in cv-qualification; neither applies. [[expr.cond#5]] requires the same value category, which is not met either. So we fall through to [[expr.cond#6]], and the result is a prvalue ([[expr.cond#6]]) of type `int`; the assertion holds.
- D: a string literal is an lvalue ([[expr.prim.literal#1]]) of type `const char[4]`; the assertion holds.

Clang reports `static assertion failed due to requirement 'std::is_same_v<void (&)(), void (&&)()>'`.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

What is the return type of `f`?

```cpp
decltype(auto) f() {
  int x = 1;
  return (x);
}
```

- A. `int`
- B. `int&`
- C. `int&&`
- D. Ill-formed: cannot return a reference to a local variable

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

1. A `decltype(auto)` return type is deduced as `decltype(E)`, where `E` is the operand of `return`, here `(x)` ([[dcl.type.auto.deduct#2.1]], [[dcl.type.auto.deduct#4]]).
2. `(x)` is parenthesized, so [[dcl.type.decltype#1.3]] (the declared type of the entity) does not apply; its value category decides.
3. `x` is a non-volatile object with automatic storage duration, an implicitly movable entity; it appears as the operand of `return` (parentheses allowed), with only block scopes in between, so this *id-expression* is move-eligible ([[expr.prim.id.unqual#15]]). A move-eligible *id-expression* is an xvalue ([[expr.prim.id.unqual#12]]).
4. `decltype` of an xvalue is `int&&` ([[dcl.type.decltype#1.5]]).

B is the answer for C++20 and earlier: then `(x)` was an lvalue and the function returned `int&`. C++23's [[P2266R3]] made a returned name an xvalue directly, and the example in [[dcl.type.auto.deduct#4]] states that `auto f2(int x) -> decltype(auto) { return (x); }` returns `int&&`.

D is wrong: returning a reference to a local variable is not ill-formed; Clang only gives a `-Wreturn-stack-address` warning, and it is the caller's use of the reference that is undefined behavior. The new C++26 ill-formedness rule ([[P2748R5]]) targets only binding a returned reference to a temporary, and `x` is not a temporary.

`static_assert(std::is_same_v<decltype(f()), int&&>)` passes on Clang 23.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
#include <initializer_list>

int main() {
  auto a = {1, 2};
  auto b{3};
  for (auto e : {4, 5}) (void)e;
  auto c = {a.size(), 6};
  return b;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.** The error is in `c`.

1. `auto a = {1, 2};` is copy-list-initialization: `auto` is replaced by `std::initializer_list<U>`, and `U` is found by template argument deduction from a function call ([[dcl.type.auto.deduct#3]]). When the argument is an initializer list, deduction is performed for each element separately ([[temp.deduct.call#1]]); both elements deduce `int`, so `a` is `std::initializer_list<int>`.
2. `auto b{3};` is direct-list-initialization, which allows only one element, and `E` is that element ([[dcl.type.auto.deduct#2.2.2]]); `b` is `int`.
3. In the range-based `for`, `{4, 5}` initializes `auto&& __range`, which also deduces `std::initializer_list<int>`; well-formed.
4. `auto c = {a.size(), 6};` deduces each element separately and gets `std::size_t` and `int`. The deductions conflict, and the declaration is ill-formed ([[dcl.type.auto.deduct#3]]).

Clang reports `deduced conflicting types ('size_t' (aka 'unsigned long') vs 'int') for initializer list element type`. Initializer-list deduction does not compute a common type and performs no conversions; it is exactly the deduction done when calling the function template `template<class U> void g(std::initializer_list<U>)` with the same argument. The draft's example `auto x2 = { 1, 2.0 };` fails for the same reason.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

Give the value category of each expression below and the result of `decltype((e))`.

```cpp
struct S { int m; int& r; static int sm; };
S make();
enum E { e1 };
void fn();
template<int N> void t();

void test(int n, int* p) {
  int arr[2] = {};
  // 1. make().r          2. make().sm          3. std::move(arr)[0]
  // 4. e1                5. n = 1              6. (1, n)
  // 7. n++               8. *p                 9. fn
  // 10. static_cast<int&&>(n)                  11. N inside the body of t
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer:**

| # | Expression | Value category | `decltype((e))` | Basis |
|---|---|---|---|---|
| 1 | `make().r` | lvalue | `int&` | When the member is a reference, `E1.E2` is always an lvalue, whatever `E1` is ([[expr.ref#8]]) |
| 2 | `make().sm` | lvalue | `int&` | Static data member: `E1.E2` is an lvalue ([[expr.ref#8.1]]) |
| 3 | `std::move(arr)[0]` | xvalue | `int&&` | Subscripting an xvalue array gives an xvalue ([[basic.lval#4.4]], under note 3) |
| 4 | `e1` | prvalue | `E` | An enumerator is not a variable; the *id-expression* is a prvalue ([[expr.prim.id.unqual#12]]) |
| 5 | `n = 1` | lvalue | `int&` | The result of built-in assignment is the left operand ([[expr.assign#1]]) |
| 6 | `(1, n)` | lvalue | `int&` | A comma expression has the value category of its right operand ([[expr.comma#1]]) |
| 7 | `n++` | prvalue | `int` | Postfix increment yields a copy of the old value ([[expr.post.incr#1]]) |
| 8 | `*p` | lvalue | `int&` | The result of indirection is an lvalue ([[expr.unary.op#1]]) |
| 9 | `fn` | lvalue | `void(&)()` | An *id-expression* naming a function is an lvalue ([[expr.prim.id.unqual#12]]) |
| 10 | `static_cast<int&&>(n)` | xvalue | `int&&` | A cast to rvalue reference to object type gives an xvalue ([[basic.lval#4.3]], under note 3) |
| 11 | `N` | prvalue | `int` | A constant template parameter of non-class type is not an object; the *id-expression* is a prvalue ([[expr.prim.id.unqual#12]]) |

The ones people get wrong are 1 and 2: a common misconception is that every member of a temporary is an xvalue. [[expr.ref#8]] handles reference members first, then static members, and only for a non-reference non-static data member does the value category of `E1` matter. The flip side of item 11 is a constant template parameter of class type: it names a template parameter object and is an lvalue.

Writing each line as `static_assert(std::is_same_v<decltype((e)), …>)`, all of them pass on Clang 23.

</details>
</div>

## 5. Copy elision, implicit move, erroneous behavior and static initialization

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program. `Pinned` can be neither copied nor moved.

```cpp run
struct Pinned {
  Pinned() = default;
  Pinned(const Pinned&) = delete;
  Pinned(Pinned&&) = delete;
  int v = 7;
};

Pinned make() { return Pinned{}; }
Pinned relay() { return make(); }

int main() {
  Pinned a = relay();
  Pinned b = Pinned(Pinned(make()));
  Pinned* p = new Pinned(make());
  Pinned arr[2] = {make(), relay()};
  int r = a.v + b.v + p->v + arr[1].v;
  delete p;
  return r;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.** The program returns 28.

There is only one core rule: when a class object is initialized from a prvalue of the same type (ignoring cv-qualification), the initializer expression is used to initialize the destination object directly ([[dcl.init#15.6.1]]). A prvalue is not an object until it is materialized; it is just a recipe for initializing some result object ([[basic.lval#5]]). With no intermediate object there is no copy or move, and no usable copy or move constructor is needed.

- `return Pinned{};` and `return make();`: `return` copy-initializes the result object of the function call from its operand ([[stmt.return#2]]), and the operand is a prvalue of the same type, so [[dcl.init#15.6.1]] applies. The result object of `relay()` is passed all the way through to `a`.
- `Pinned(Pinned(make()))`: a functional-notation conversion with a single expression in the parentheses is equivalent to the corresponding cast expression ([[expr.type.conv#1.1]]), here a `static_cast`, whose result object is initialized directly from the operand ([[expr.static.cast#5]]): [[dcl.init#15.6.1]] again. The draft's example `T x = T(T(T()));` is about exactly this.
- `new Pinned(make())`: the *new-initializer* is interpreted as direct-initialization ([[expr.new#24.2]]); same as above.
- Array elements are copy-initialized from the elements of the initializer list, which are prvalues of the same type; same as above.

This is not permitted copy elision, and [[class.copy.elision]] plays no role here: there is no object being elided. What [[class.copy.elision#1.1]] allows to be elided is only the copy of a named local variable, which has nothing to do with these prvalues.

<div class="compare" markdown="1">

```cpp ok
Pinned make() { return Pinned{}; }   // prvalue
```

```cpp error
Pinned make() {
  Pinned p;
  return p;    // error: needs the move constructor, which is deleted
}
```

</div>

For walkthroughs see [[papers/guaranteed-copy-elision]] and [[topics/value-categories]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program against the current draft. `M` can only be moved, not copied.

```cpp run
struct M {
  M() = default;
  M(M&&) = default;
  M(const M&) = delete;
};

struct Holder { Holder(M) { } };

M from_ref(M&& r) { return r; }
M paren() { M m; return (m); }
Holder convert() { M m; return m; }
int&& pass(int&& x) { return x; }

int main() {
  M a = from_ref(M{});
  M b = paren();
  Holder h = convert();
  (void)a; (void)b; (void)h;
  return pass(1) - 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

All four `return`s rely on the same rule: if an *id-expression* names an implicitly movable entity (a non-volatile object with automatic storage duration, or an rvalue reference to a non-volatile object type), appears as the operand of `return` (possibly parenthesized), and only block scopes lie in between, it is move-eligible ([[expr.prim.id.unqual#15]]), and a move-eligible *id-expression* is an xvalue ([[expr.prim.id.unqual#12]]).

- `from_ref`: `r` is a named rvalue reference, which is an lvalue elsewhere. But it is a variable of rvalue reference to object type, an implicitly movable entity, so the `r` in `return r;` is an xvalue and the move constructor is selected.
- `paren`: `(m)` with parentheses still counts; [[expr.prim.id.unqual#15.2]] says "possibly parenthesized".
- `convert`: `m` is an xvalue and copy-initializes the result object of type `Holder`, calling `Holder(M)`, whose parameter is initialized from the xvalue using the move constructor. That the return type differs from the variable's type does not matter; the rule looks only at the expression itself.
- `pass`: `x` is an xvalue and can bind directly to the return type `int&&`. The reference returned by `pass(1)` refers to the temporary for the argument `1`, which persists until the end of the full-expression containing the call ([[class.temporary#6.10]]), so reading it within the same full-expression is fine.

Historically these four cases were relaxed in several steps: `from_ref` and `convert` were ill-formed before C++20 ([[P1825R0]]), and `pass` was ill-formed before C++23 ([[P2266R3]]). Compiled with `-std=c++20`, Clang rejects only `pass`: `rvalue reference to type 'int' cannot bind to lvalue of type 'int'`. For the evolution see [[papers/implicit-move]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this translation unit.

```cpp
struct M {
  M() = default;
  M(M&&) = default;
  M(const M&) = delete;
};

M pick(bool b) {
  M x, y;
  if (b) return x;
  return [&] { return y; }();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.** The error is the `return y;` inside the lambda.

1. `return x;`: `x` satisfies the three conditions of [[expr.prim.id.unqual#15]], is an xvalue, and uses the move constructor; well-formed.
2. The lambda captures by reference, and the `y` in `return y;` still names `pick`'s local variable `y`, which is itself an implicitly movable entity. But [[expr.prim.id.unqual#15.3]] requires every intervening scope between the declaration of `y` and this expression to be a block scope, and here the lambda's function parameter scope lies in between, which is not a block scope. So `y` is not move-eligible; it is an lvalue.
3. The lambda's return type is deduced as `M`, and the result object is copy-initialized from the lvalue `y`, which needs the copy constructor, which is deleted ([[dcl.fct.def.delete#2]]).
4. The outer `return [&]{…}();` has a prvalue operand and benefits from guaranteed copy elision; it is fine by itself.

The restriction makes sense: the lambda might be called several times before `pick` returns, and silently moving from the outer variable would change what later calls see.

Also ill-formed for the same reason are `return b ? x : y;` (a conditional expression is not an *id-expression*, so [[expr.prim.id.unqual#15.2]] is not satisfied) and returning a static local variable (not automatic storage duration, so [[expr.prim.id.unqual#15.1]] is not satisfied). Clang reports `call to deleted constructor of 'M'` for both.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program against the current draft.

```cpp
int main() {
  unsigned char c [[indeterminate]];
  unsigned char d = c;
  c = d;
  unsigned char e = true ? c : d;
  (void)e;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed, with defined behavior.**

1. `c` is marked `[[indeterminate]]`, so its bytes have indeterminate values rather than erroneous values ([[basic.indet#1.1]], [[dcl.attr.indet#1]]). In general, an evaluation that produces an indeterminate value is undefined behavior ([[basic.indet#2]]).
2. But [[basic.indet#2]] lists exceptions for unsigned ordinary character types and `std::byte`:
    - Initializing an `unsigned char` object with an indeterminate value gives that object an indeterminate value ([[basic.indet#2.3]]). `d = c` is this case.
    - If the right operand of a simple assignment is an indeterminate value and the left operand is an `unsigned char` lvalue, the object referred to by the left operand gets an indeterminate value ([[basic.indet#2.2]]). `c = d` is this case.
    - If the second or third operand of a conditional expression produces an indeterminate value, so does the result ([[basic.indet#2.1.1]]); initializing `e` with it is again [[basic.indet#2.3]].
3. `(void)e` is a discarded-value expression ([[basic.indet#2.1.4]]).

Throughout, indeterminate values are only moved between `unsigned char`s, and no evaluation falls outside the exceptions, so there is no undefined behavior. Remove `[[indeterminate]]` and `c` holds an erroneous value; the same exceptions apply to erroneous values, so the conclusion is unchanged.

The exceptions end as soon as the value is used for anything else:

```cpp ub
unsigned char c [[indeterminate]];
unsigned char d = c;
int i = d;       // integral promotion produces an indeterminate value: undefined behavior
```

Remove `[[indeterminate]]` here and the last line becomes erroneous behavior.

Clang 23 does not recognize `[[indeterminate]]`; it warns `unknown attribute 'indeterminate' ignored` and gives a `-Wuninitialized` warning for `d = c`. Neither affects the verdict under the draft. See [[papers/erroneous-behaviour]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does this program print? The whole program consists of this one translation unit.

```cpp run
#include <cstdio>

extern int b;
int a = b + 1;
int b = 41;

int main() { std::printf("%d\n", a); }
```

- A. `1`
- B. `42`
- C. `1` or `42`, unspecified
- D. Undefined behavior: `a` reads `b` before `b` is initialized

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

1. The initializer `41` of `b` is a constant expression, so `b` is constant-initialized ([[expr.const.init#4]], [[expr.const.init#5]]); constant initialization is performed, which is static initialization ([[basic.start.static#2]]).
2. The initializer `b + 1` of `a` performs an lvalue-to-rvalue conversion on `b`, and `b` is not const and cannot be used in constant expressions, so `b + 1` is not a core constant expression ([[expr.const.core#2.10]]). `a` is not constant-initialized; it is zero-initialized first and then dynamically initialized.
3. All static initialization strongly happens before any dynamic initialization ([[basic.start.static#2]]). So when `a` is dynamically initialized, `b` is already 41, and `a` is 42.
4. An implementation may turn `a`'s initialization into static initialization too, but only if the result is the same as with dynamic initialization ([[basic.start.static#3]]), so it is still 42.

Distractor C corresponds to a different program: only if `b` itself also needed dynamic initialization would the result depend on the implementation. Note 2 in [[basic.start.static#3]] gives exactly such an example:

```cpp unspecified
inline int g() { return 41; }
extern int b;
int a = b + 1;   // 1 or 42
int b = g();
```

Here `b` has dynamic initialization, ordered after `a` by definition order ([[basic.start.dynamic#3]]), but the implementation may hoist it into static initialization. Only when `b` is statically initialized and `a` dynamically initialized does `a` read 41, giving 42; in every other case the result is 1: if `b` is dynamically initialized, `a` reads the zero-initialized 0; if `a` is also hoisted into static initialization, its value must equal what it would have been had every variable not required to be statically initialized been dynamically initialized ([[basic.start.static#3.2]]), which is again 1. Clang 23 prints 1 at both `-O0` and `-O2`.

D is wrong: `b` has static storage duration, so its storage exists and is initialized before any code runs, and reading it is not undefined behavior.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

For each numbered line in `main`, say which constructors are called, and which of them the standard requires never to happen, which may be elided, and which must happen.

```cpp run
#include <cstdio>
#include <utility>

struct S {
  S() { std::puts("S()"); }
  S(const S&) { std::puts("S(const S&)"); }
  S(S&&) { std::puts("S(S&&)"); }
  ~S() { std::puts("~S()"); }
};

S f() { return S(); }
S g() { S s; return s; }
S h(S p) { return p; }
void take(S) { }

int main() {
  S a = f();                // 1
  S b = g();                // 2
  take(S());                // 3
  S c = std::move(S());     // 4
  S d = h(S());             // 5
  const S& e = S();         // 6
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer:**

| Line | Constructions | Nature | Basis |
|---|---|---|---|
| 1 | `S()` | Exactly one construction; no copy or move is possible | `S()` and `f()` are both prvalues of the same type, and `a` is the result object ([[dcl.init#15.6.1]]) |
| 2 | `S()`, possibly plus `S(S&&)` | The move may be elided | Named return value optimization ([[class.copy.elision#1.1]]); if not elided, `s` is move-eligible and is moved, not copied ([[expr.prim.id.unqual#15]]) |
| 3 | `S()` | Exactly one construction | The parameter is copy-initialized from a prvalue of the same type, so [[dcl.init#15.6.1]] applies |
| 4 | `S()`, `S(S&&)` | Both must happen | The argument of `std::move` materializes the prvalue into a temporary ([[dcl.init.ref#5.3]]) and an xvalue is returned; `c` is initialized from the xvalue, the move constructor is selected, and there is no room for elision |
| 5 | `S()`, `S(S&&)` | Both must happen | The argument directly initializes the parameter `p`; the `p` in `return p;` is a function parameter, which [[class.copy.elision#1.1]] explicitly excludes, so it cannot be elided; `p` is move-eligible and is moved |
| 6 | `S()` | Exactly one construction | The prvalue is materialized into a temporary, the reference binds directly, and the lifetime is extended to that of `e` ([[class.temporary#6.1]]) |

Some key points:

- Lines 1 and 3 are not copy elision. Since C++17 a prvalue is no longer a temporary, and the elision [[class.copy.elision]] talks about is only the named-object case of line 2. Compiled with `-fno-elide-constructors`, the output of lines 1 and 3 is unchanged; only line 2 gains an `S(S&&)` and a following `~S()`.
- Line 4 is the well-known pessimizing move: `std::move` turns a prvalue that could have initialized `c` directly into an xvalue, forcing an extra move. Clang flags it with `-Wpessimizing-move`.
- Line 5 shows that a by-value parameter cannot get named return value optimization: the caller arranges the parameter's storage, so the function cannot construct it in the return value's location. Since C++11 it is at least moved rather than copied.

In our tests with Clang 23's default output, line 2 calls only `S()`; lines 4 and 5 each have one `S(S&&)` followed immediately by a `~S()` (on line 4 the moved-from temporary is destroyed at the end of the full-expression; on line 5 the parameter `p` is destroyed). At the end of the program the 5 objects are destroyed in reverse order: `e`, `d`, `c`, `b`, `a`. For more line-by-line traces see [[topics/special-members-and-elision]].

</details>
</div>

## Questions and clauses

| No. | Topic | Clauses |
|---|---|---|
| 1 | Out-of-class `= default` is user-provided; value-initialization without zeroing; erroneous values | [[dcl.init#8]], [[dcl.fct.def.default#5]], [[basic.indet#2]] |
| 2 | Default-initialization of const objects | [[dcl.init#7]] |
| 3 | Aggregates, value-initialization, `new T()`, zero-initialization with thread storage duration | [[dcl.init.aggr#6]], [[dcl.init#8]], [[expr.new#24]], [[basic.start.static#2]] |
| 4 | The most vexing parse | [[dcl.ambig.res#1]], [[dcl.fct#5]] |
| 5 | Constant exceptions to narrowing; `nullptr` to `bool` | [[dcl.init.list#7]], [[dcl.init#15.8]] |
| 6 | Initializer-list constructors first; copying into the backing array | [[over.match.list#1]], [[dcl.init.list#5]] |
| 7 | Nested braces select the iterator-range constructor | [[over.match.list#1]], [[iterator.requirements.general#12]] |
| 8 | Deleted default constructors and the aggregate definition | [[dcl.init.aggr#1]], [[dcl.init.list#3.5]] |
| 9 | Parenthesized aggregate initialization: narrowing and temporary lifetime | [[dcl.init#15.6.2.2]], [[class.temporary#6.11]] |
| 10 | Designated initializers and aggregate bases | [[dcl.init.aggr#4.1]], [[dcl.init.list#3.1]] |
| 11 | How the aggregate definition changed between C++17 and C++20 | [[dcl.init.aggr#1]], [[over.match.ctor#1]], [[dcl.init#15.6.2.2]] |
| 12 | Copy-list-initialization choosing an explicit constructor | [[over.match.list#1]], [[over.match.copy#1]] |
| 13 | Explicit conversion functions and direct-initialization | [[dcl.init#15.7]], [[over.match.conv#1]], [[conv.general#4]] |
| 14 | An rvalue reference bound to a converted temporary | [[dcl.init.ref#5.4]] |
| 15 | Bit-fields and non-const references | [[dcl.init.ref#5.2]], [[class.bit#3]] |
| 16 | Value categories and `decltype` | [[dcl.type.decltype#1]], [[expr.ref#8]], [[expr.call#15]], [[expr.cond#6]] |
| 17 | `decltype(auto)` and move-eligibility | [[dcl.type.auto.deduct#4]], [[expr.prim.id.unqual#15]] |
| 18 | `auto` deduction from initializer lists | [[dcl.type.auto.deduct#3]], [[temp.deduct.call#1]] |
| 19 | Classifying expressions by value category | [[basic.lval#4]], [[expr.ref#8]], [[expr.prim.id.unqual#12]] |
| 20 | Guaranteed copy elision | [[dcl.init#15.6.1]], [[basic.lval#5]] |
| 21 | The reach of implicit move | [[expr.prim.id.unqual#15]], [[class.temporary#6.10]] |
| 22 | Lambdas and conditional expressions do not trigger implicit move | [[expr.prim.id.unqual#15]] |
| 23 | `[[indeterminate]]` and the `unsigned char` exceptions | [[basic.indet#2]], [[dcl.attr.indet#1]] |
| 24 | Static initialization before dynamic initialization | [[basic.start.static#2]], [[basic.start.static#3]] |
| 25 | Copy elision, materialization and moves combined | [[dcl.init#15.6.1]], [[class.copy.elision#1]], [[class.temporary#6]] |
