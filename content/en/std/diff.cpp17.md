---
title: C++ and ISO C++ 2017
summary: "What previously valid code breaks or changes behavior when moving from C++17 to C++20: lines starting with module or import, new keywords, the <=> token, u8 literals becoming char8_t, the new definition of aggregates, reversed == candidates, f < a being treated as a template name, the removal of throw(), and changes to iostreams, filesystem, containers and a batch of deprecated library facilities."
updated: 2026-10-19
---

!!! tldr
    - C++20 adds the keywords `concept`, `requires`, `char8_t`, `consteval`, `constinit` and three `co_` keywords; lines starting with `module` or `import` are treated as module directives; and `<=` immediately followed by `>` forms `<=>`.
    - The type of `u8"..."` changes from an array of `const char` to an array of `const char8_t`; code that uses it as a `const char*` or `std::string`, or writes it to `std::cout`, has to change.
    - A class that declares any constructor (including `= default` and `= delete`) is no longer an aggregate, so `struct P { P() = default; int x, y; }; P p{1, 2};` fails to compile.
    - `a == b` also tries `operator==` with the arguments swapped, and `a != b` also tries the rewritten form `!(a == b)`. An asymmetric `operator==`, or one missing `const`, may become ambiguous or silently call a different function.
    - In the library: `throw()` is removed, iostreams reject output of `u8`, `char16_t` and similar characters and unbounded reads into `char*`, and deprecated facilities such as `uncaught_exception`, `not1`, `result_of` and the redundant members of `std::allocator` are removed.

[diff.cpp17] lists the incompatibilities of C++20 relative to C++17: previously well-formed code that becomes ill-formed in C++20, or whose meaning changes. Every entry in the standard has the same format: the affected subclause, what changed, why, and the effect on old code. C++20 added modules, concepts, coroutines, three-way comparison and `char8_t`, each of which took over a piece of old syntax, so this subclause has more entries than the other versions.

¶1 This subclause lists differences in addition to those in the subclauses above: to upgrade from C++17 to the current draft you also need to read [[diff.cpp20]], [[diff.cpp23]] and [[diff.cpp26]]. Entries follow the order of the chapters in the main text. All tests on this page use Clang 23.1.3 with libc++, comparing `-std=c++17` with `-std=c++20`. With `-Wc++20-compat` under `-std=c++17`, Clang warns about several of these in advance.

## Lexical conventions [diff.cpp17.lex] {#diff.cpp17.lex}

### Lines starting with `module` or `import`

```cpp
class module {};
module m1;     // C++20: a module declaration, no longer a variable declaration
module *m2;    // still a variable declaration

class import {};
import j1;     // C++20: a module import declaration
::import j2;   // still a variable declaration
```

¶1 In C++20, a logical line starting with `module` or `import` is recognized by the preprocessor as a module directive ([[lex.pptoken]], [[module.unit]], [[module.import]], [[cpp.module]], [[cpp.import]]). `module` and `import` are not keywords but **identifiers with special meaning**: they have a special meaning only in these positions and can still be used as names elsewhere.

So `module m1;` no longer declares a variable; it becomes a (misplaced) module declaration. When the next token is one that cannot appear in a module directive, such as `*` or `::`, nothing changes. The fix is to put `::` before the type name, or to rename. Clang 23 reports module declaration must occur at the start of the translation unit for `module m1;`.

### `<...>` after `import`

```cpp
template<typename> class import {};
import<int> f();     // error: treated as importing the header <int>
::import<int> g();   // OK
```

¶2 C++20 can import header units with `import <vector>;`, so when the identifier `import` is followed by `<`, the `<...>` is lexed as a header-name token ([[lex.header]]). The second line above therefore imports a header named `int`, and Clang 23 reports 'int' file not found. Adding `::` fixes it.

### New keywords

```cpp
bool requires = true;   // error: requires is a keyword in C++20
int concept = 0;        // error
char char8_t = 0;       // error
```

¶3 C++20 adds the keywords `char8_t`, `concept`, `consteval`, `constinit`, `co_await`, `co_yield`, `co_return` and `requires` ([[lex.key]]), breaking code that uses them as identifiers. `requires` and `concept` are not unusual as variable names in old code. Renaming is enough, though there may be a lot of it. With `-Wc++20-compat` under `-std=c++17`, Clang warns is a keyword in C++20 at every occurrence.

### New token `<=>`

<div class="compare" markdown="1">

```cpp error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;    // error
}
```

```cpp ok
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<= > y;   // OK
}
```

</div>

¶4 The three-way comparison operator `<=>` is a new token in C++20 ([[lex.operators]]). Tokenization takes the longest token, so the adjacent `<=` and `>` of C++17 now form one `<=>`. The left side means to pass the function `operator<=` as a template argument, but in C++20 it becomes `operator<=>`. Adding a space fixes it.

Clang 23 gives a `-Wc++20-compat` warning under `-std=c++17` suggesting a space, and an error under `-std=c++20`.

### UTF-8 literals change type to `char8_t`

```cpp
const auto* u8s = u8"text";   // deduced as const char8_t* (C++17: const char*)
const char* ps = u8s;         // error

auto u8c = u8'c';             // deduced as char8_t (C++17: char)
char* pc = &u8c;              // error

std::string s = u8"text";     // error

void f(const char* s);
f(u8"text");                  // error

template<typename> struct ct;
template<> struct ct<char> { using type = char; };
ct<decltype(u8'c')>::type x;  // error: ct<char8_t> is not defined
```

¶5 C++20 adds the character type `char8_t`. The type of `u8"..."` changes from array of `const char` to array of `const char8_t`, and the type of `u8'c'` from `char` to `char8_t` ([[lex.string]], [[lex.ccon]]). This lets overloading, template specialization and type deduction distinguish ordinary literals from UTF-8 literals. The cost is that all code using `u8` literals as `char` strings breaks.

There are several possible fixes. If the execution character set is already UTF-8, drop the `u8` prefix; where the interface can change, use `std::u8string_view`; as a stopgap, use `reinterpret_cast<const char*>(u8"...")`. Clang and GCC also offer the non-standard option `-fno-char8_t`, which restores the C++17 semantics. C++23 again allows `u8` literals to initialize `char` arrays; see the [dcl] section of [[diff.cpp20]].

## Basics [diff.cpp17.basic] {#diff.cpp17.basic}

### A pseudo-destructor call ends the object's lifetime

```cpp ub
int f() {
  int a = 123;
  using T = int;
  a.~T();
  return a;   // UB: a's lifetime has ended; C++17 returns 123
}
```

¶1 Calling a destructor on a scalar type such as `int` is a **pseudo-destructor call** ([[g:pseudo-destructor]]). In C++17 it did nothing; C++20 says it ends the object's lifetime ([[basic.life]]). That way, when generic code writes `p->~T()` for an arbitrary `T`, it means the same thing whether `T` is a class or a scalar: the object ends here. Reading `a` afterwards reads an object outside its lifetime, and the behavior is undefined.

Run on Clang 23, both modes return 123, which is one way UB can show up. Making `f` `constexpr` and calling it in a constant expression, Clang reports read of object outside its lifetime under `-std=c++20`, confirming the new rule.

### Release sequences consist only of read-modify-write operations

```cpp
std::atomic<int> flag{0};
int data = 0;

// thread 1
data = 42;
flag.store(1, std::memory_order_release);
flag.store(2, std::memory_order_relaxed);

// thread 2
if (flag.load(std::memory_order_acquire) == 2)
  use(data);   // C++20: data race with data = 42; C++17: synchronized
```

¶2 After a release write, some later modifications of the same atomic variable still count as continuing that write, and an acquire read that sees them also synchronizes with the release write. This chain of modifications is the **release sequence** ([[g:release-sequence]], [[intro.races]]). In C++17, later ordinary writes to the variable by the same thread were included; C++20 says that, apart from the initial release operation, a release sequence contains only atomic read-modify-write operations (such as `fetch_add` and `exchange`).

So in the example above, when thread 2 reads 2 it no longer synchronizes with thread 1's release write, and reading `data` is a data race, even if no other thread wrote `flag` in between. The feature was rarely used and confusing, so it was removed. Compilers do not diagnose this; the fix is to make the second write `memory_order_release` too.

## Expressions [diff.cpp17.expr] {#diff.cpp17.expr}

### Implicit lambda capture may capture more entities

```cpp
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;   // n is captured whatever B and sizeof(int) are
    }
  }(0);
}
```

¶1 A lambda with a capture-default (`[=]` or `[&]`) automatically captures the local entities used in its body. C++17 captured an entity only when it was odr-used (roughly, when its address or run-time value is needed); C++20 decides syntactically instead: if it is named in a potentially-evaluated expression, it is captured, even if that expression is in a discarded `if constexpr` branch ([[expr.prim.lambda.capture]]).

With the odr-use rule, which variables a generic lambda captures was known only after instantiation, so the layout of the closure type depended on instantiation, and the interaction with `if constexpr` was unclear. The syntactic rule is simpler; the cost is that closures may be larger and copy a few more objects. Captures that are not odr-used can be optimized away by the implementation.

Clang 23 captures `n` in both modes (closure size 4), so it applies this fix to C++17 mode too. This change usually requires no code changes.

## Declarations [diff.cpp17.dcl.dcl] {#diff.cpp17.dcl.dcl}

### An unnamed class named by a typedef can contain only C-compatible members

```cpp error
typedef struct {
  void f() {}   // error: well-formed in C++17
} S;
```

¶1 In `typedef struct { ... } S;`, the unnamed class gets the name it uses for linkage from the typedef name `S`; this is a **typedef name for linkage purposes** ([[g:typedef-name-for-linkage]], [[dcl.typedef]]). C++20 says such a class can only have non-static data members, member enumerations and member classes; it cannot have member functions, base classes, default member initializers or lambda expressions. In other words, it can contain only things that also exist in C.

The reason is implementability. The class's linkage name is only known when the `S` at the end is read, but entities such as member functions in the class body need a definite name before that, for name mangling for instance. The fix is to name the class: `struct S { ... };`. Clang 23 gives only a `-Wnon-c-typedef-for-linkage` warning in both modes; a warning for an ill-formed program counts as a diagnostic, so this conforms.

### A function cannot have different default arguments in different translation units

```cpp title="tu1.cpp"
int f(int a = 42);
int g() { return f(); }
```

```cpp title="tu2.cpp" ifndr
int f(int a = 76) { return a; }   // different from the default argument in tu1.cpp
int g();
int main() { return g(); }        // returns 42 in C++17
```

¶2 C++20 says that when declarations of the same function in different translation units give default arguments for the same parameter, those default arguments must be the same ([[dcl.fct.default]]). Modules need this rule: a default argument may reach many translation units through a module interface, and its meaning must be unique.

A program that violates this rule is **ill-formed, no diagnostic required** (IFNDR): the compiler sees one translation unit at a time and cannot see the conflict, the linker does not complain either, and yet the standard no longer guarantees any result. The fix is to put the default argument only on the one declaration in the header.

### A class with user-declared constructors is no longer an aggregate

```cpp
struct A { A() = delete; };                 // an aggregate in C++17, not in C++20
struct B { B() = default; int i = 0; };     // likewise
struct C { C(C&&) = default; int a, b; };   // likewise

A a{};                  // error: well-formed in C++17
B b = {1};              // error
auto* c = new C{2, 3};  // error

struct Y;
struct X { operator Y(); };
struct Y {              // an aggregate in C++17, not in C++20
  Y(const Y&) = default;
  X x;
};
Y y{X{}};   // C++20: calls the copy constructor via X::operator Y
            // C++17: aggregate initialization, y.x initialized from X{}
```

¶3 An **aggregate** is a class whose members can be initialized one by one with braces, such as `struct P { int x, y; }; P p{1, 2};` ([[dcl.init.aggr]]). C++17 required an aggregate to have no user-provided constructors; C++20 changes this to no user-declared constructors, so a constructor written as `= default` or `= delete` also makes the class not an aggregate.

Under the old rule, a class that declared `A() = delete;` could still be written `A a{};`, and aggregate initialization completely bypassed the author's intent to forbid default construction. The new rule closes this hole.

The most common casualty in real code is `struct P { P() = default; int x, y; }; P p{1, 2};`. That `= default` line was redundant anyway; delete it and the class is an aggregate again. If the constructor serves some other purpose, add a real constructor that accepts those arguments. Clang 23 implements this: under `-std=c++20` the `A`, `B` and `C` lines are all errors.

### Conversion from a pointer to `bool` is narrowing

```cpp error
bool y[] = { "bc" };   // error: well-formed in C++17
```

¶4 Brace initialization does not allow implicit conversions that may lose information; these are **narrowing conversions** ([[g:narrowing-conversion]], [[dcl.init.list]]). C++20 counts conversion from a pointer or pointer-to-member to `bool` as narrowing too, to catch mistakes like the one above: probably meant as a string, it yields `true`. When you want a truth value, write `p != nullptr`. Clang 23 treats this as a defect fix and reports an error under `-std=c++17` as well.

## Classes [diff.cpp17.class] {#diff.cpp17.class}

### `explicit` cannot be followed directly by a parenthesized constructor name

```cpp
struct S {
  explicit (S)(const S&);      // error: well-formed in C++17
  explicit (operator int)();   // error
  explicit(true) (S)(int);     // OK
};
```

¶1 C++20 introduces the conditional `explicit(condition)`, so parentheses immediately after `explicit` are parsed as the condition ([[class.ctor]], [[class.conv.fct]]). In C++17 a constructor or conversion function name could be parenthesized, and `explicit (S)(const S&)` was valid; in C++20 `(S)` is taken as the condition and the program is ill-formed. Removing the redundant parentheses fixes it.

### A constructor name cannot be written `A<T>`

```cpp error
template<class T>
struct A {
  A<T>();    // error: well-formed in C++17
  A(int);    // OK: uses the injected-class-name
  ~A<T>();   // error
};
```

¶2 When declaring a constructor or destructor inside a class template, C++20 no longer allows the form with template arguments such as `A<T>`; only the injected-class-name `A` may be used ([[class.ctor]], [[class.dtor]]). This redundant form was error-prone and was removed; deleting the `<T>` is enough.

Clang 23 does not implement this restriction yet; under `-std=c++20` there is no diagnostic at all, even with `-pedantic`.

### Implicit move applies in more places

```cpp
struct base {
  base();
  base(base const&);
private:
  base(base&&);
};
struct derived : base {};

base f(base b) {
  throw b;     // error: base(base&&) is private
  derived d;
  return d;    // error: base(base&&) is private
}
```

¶3 C++20 widens implicit move in two places ([[class.copy.elision]]). First, when returning a movable local object, a constructor taking an rvalue reference to a different type can be called, for example `base`'s move constructor when returning a local `derived`. Second, function parameters and catch-clause parameters can also be moved by `throw`.

Places that used to select the copy constructor now select the move constructor, and if the move constructor is inaccessible, compilation fails, as above. When moving and copying have different effects, behavior changes too:

```cpp
struct S {
  S(const char* s) : m(s) { }
  S(const S&) = default;
  S(S&& other) : m(other.m) { other.m = nullptr; }
  const char* m;
};

S consume(S&& s) { return s; }   // C++20: moves s, i.e. the caller's object

void g() {
  S s("text");
  consume(static_cast<S&&>(s));
  char c = *s.m;   // UB: s.m has been nulled; in C++17 s was copied and this was fine
}
```

The parameter `s` of `consume` is an rvalue reference, and in C++20 `return s;` moves the object it refers to, which is the `s` in `g`. Clang 23 applies this change to C++17 mode as well: `f` is an error in both modes, and `s.m` in `g` is a null pointer in both modes.

## Overloading [diff.cpp17.over] {#diff.cpp17.over}

### `==` and `!=` use candidates with reversed arguments

```cpp
struct A {
  operator int() const;
};

bool operator==(A, int);   // #1
// built-in candidate #2: bool operator==(int, int);
// built-in candidate #3: bool operator!=(int, int);

int check(A x, A y) {
  return (x == y) +   // C++20: ambiguous; C++17: calls #1
    (10 == x) +       // C++20: calls #1 (reversed); C++17: #2
    (10 != x);        // C++20: calls #1 (rewritten as !(x == 10)); C++17: #3
}
```

¶1 In C++20, besides `operator==(x, y)`, `x == y` also considers `operator==(y, x)` with the arguments reversed; `x != y` also considers `!(x == y)`, rewritten from `operator==`, and its reversed form. These are **rewritten candidates** ([[g:rewritten-candidate]], [[over.match.oper]]). This way a single `operator==` supports all four equality comparisons, consistent with the design of three-way comparison `<=>`.

As a result, when one type is implicitly convertible to another, `==` and `!=` may call a different function. In the example above, `10 == x` used the built-in integer comparison and now uses #1. `x == y` becomes ambiguous: the forward #1 needs to convert `y` to `int`, the reversed #1 needs to convert `x` to `int`, and the two are equally good.

¶2 Comparing two objects of the same type can also become ambiguous:

```cpp
struct B {
  bool operator==(const B&);   // missing const
};
B b1;
bool eq = (b1 == b1);          // C++20: ambiguous; well-formed in C++17
```

The implicit object parameter of the forward candidate `b1.operator==(b1)` is a non-const `B&`, and its second parameter is `const B&`; the reversed candidate is the opposite. Each candidate is better on one argument, so the call is ambiguous. Adding `const` to the member `operator==` fixes it; it should have been there all along.

For both ambiguities, Clang 23 gives only a `-Wambiguous-reversed-operator` warning and then picks a function as usual. A warning is a diagnostic, so this conforms. With a print added to #1, `10 == x` and `10 != x` use the built-in comparison under `-std=c++17`, and both call #1 under `-std=c++20`. The compiler says nothing about such changes of call target; they need to be checked by hand.

## Templates [diff.cpp17.temp] {#diff.cpp17.temp}

### A function name followed by `<` is treated as a template name

```cpp
struct A {};
bool operator<(void (*fp)(), A);
void f() {}
int main() {
  A a;
  f < a;     // error: well-formed in C++17
  (f) < a;   // OK
}
```

¶1 C++20 says that if an unqualified name is followed by `<` and name lookup finds nothing or finds a function, the name is treated as a template name ([[temp.names]]).

This allows function templates with explicit template arguments to be called through argument-dependent lookup (ADL), as in `get<0>(t)`. In C++17, if ordinary lookup could not see any template named `get`, `get < 0` was taken as less-than, and you had to bring in a template of the same name with `using` first. The cost is that `f < a` above is taken as the start of a template argument list, and the program is ill-formed. Parentheses fix it.

## Exception handling [diff.cpp17.except] {#diff.cpp17.except}

### `throw()` removed

```cpp error
void f() throw();   // error: change to void f() noexcept;
```

¶1 C++20 removes the exception specification `throw()` ([[except.spec]]). Since C++17 it has meant the same as `noexcept`, so replace it directly. Dynamic exception specifications with types, `throw(int)`, were already removed in C++17; see [[diff.cpp14]].

The standard also notes that there is no way to say "does not throw" that works in both the current standard and C++03; headers that need to be compatible with both have to generate different code with the preprocessor based on `__cplusplus`.

Clang 23 does not implement this yet: `void f() throw();` is accepted under `-std=c++20` and even `-std=c++2c`; only with `-Wdeprecated` is there a deprecation warning.

## Library introduction [diff.cpp17.library] {#diff.cpp17.library}

¶1 C++20 adds the headers `<barrier>`, `<bit>`, `<charconv>`, `<compare>`, `<concepts>`, `<coroutine>`, `<format>`, `<latch>`, `<numbers>`, `<ranges>`, `<semaphore>`, `<source_location>`, `<span>`, `<stop_token>`, `<syncstream>` and `<version>` ([[headers]]). Watch out for `<version>`: some projects have a file named `version` (or, on case-insensitive file systems, `VERSION`) in their include path, and since other standard library headers include `<version>`, picking up the wrong file produces baffling errors.

¶2 C++20 removes the five empty headers `<ccomplex>`, `<ciso646>`, `<cstdalign>`, `<cstdbool>` and `<ctgmath>`. Their existence implied that C++ headers need to be compatible with C, which is not a requirement. Replace `<ccomplex>` with `<complex>` and `<ctgmath>` with `<cmath>` plus `<complex>`, and simply delete the other three. In our tests libc++ still provides all five headers in C++20 mode, without warnings.

## Containers library [diff.cpp17.containers] {#diff.cpp17.containers}

¶1 The return type of `remove`, `remove_if` and `unique` in `list` and `forward_list` changes from `void` to `size_type`, returning the number of elements removed ([[forward.list]], [[list]]). Code that depends on the return type, for example taking a member function pointer or using `decltype`, may change meaning. Mixing translation units compiled as C++17 and C++20 may fail to link or have undefined behavior. libc++ implements this in our tests: `decltype(std::list<int>{}.remove(1))` is `void` under C++17 and `unsigned long` under C++20.

## Iterators library [diff.cpp17.iterators] {#diff.cpp17.iterators}

¶1 The specializations of `iterator_traits` for `void*` and function pointer types no longer have any nested types ([[iterator.traits]]), so that pointers that cannot be incremented are not mistaken for iterators. Code that relies on these nested types may fail to compile or change behavior. In our tests, with libc++, accessing `iterator_traits<void*>::value_type` produces a hard error inside the library under C++17, while under C++20 it is an ordinary missing member that SFINAE can detect.

## Algorithms library [diff.cpp17.alg.reqs] {#diff.cpp17.alg.reqs}

¶1 The number and order of deducible template parameters in algorithm declarations change from matching the declaration to unspecified ([[algorithms.requirements]]). This lets implementations write some algorithms as function objects with a templated call operator, which is how the algorithms in `std::ranges` are implemented. Code that writes explicit template arguments for an algorithm (such as `std::find<It, int>(...)`) may fail to compile or have undefined behavior, unless the algorithm explicitly allows it. Let the template arguments be deduced.

## Input/output library [diff.cpp17.input.output] {#diff.cpp17.input.output}

### Reading into a character array accepts only arrays

```cpp
auto p = new char[100];
char q[100];
std::cin >> std::setw(20) >> p;   // error: well-formed in C++17
std::cin >> std::setw(20) >> q;   // OK
```

¶1 `operator>>(basic_istream&, charT*)` changes to `operator>>(basic_istream&, charT(&)[N])` ([[istream.extractors]]). The library thus knows the size of the target array and will not write out of bounds even if you forget `setw`. Reading into the buffer a pointer points to is no longer allowed; read into a `std::string` instead, or use an array.

### Writing `u8` and other character types to an `ostream`

```cpp
std::cout << u8"text";   // error: in C++17 prints the string
std::cout << u8'X';      // error: in C++17 prints the character
std::cout << u"text";    // error: in C++17 prints the pointer value
std::cout << u'X';       // error: in C++17 prints the integer 88
```

¶2 Once `u8` literals have type `char8_t`, if nothing were done, `cout << u8"text"` would select the `const void*` overload and print an address, and `cout << u8'X'` would print an integer. So C++20 defines the insertion operators of `basic_ostream<char>` and `basic_ostream<wchar_t>` for `char8_t` characters and strings as deleted ([[ostream.inserters.character]]).

¶3 For the same reason, the insertion operators of `basic_ostream<char>` for `wchar_t`, `char16_t` and `char32_t`, and of `basic_ostream<wchar_t>` for `char16_t` and `char32_t`, are also deleted. In C++17, `cout << u"text"` printing a pointer value and `cout << u'X'` printing 88 were not what anyone wanted. libc++ implements this in our tests; all of these report selected deleted operator under C++20.

### `path::u8string()` returns `std::u8string`

```cpp
std::filesystem::path p;
std::string s1 = p.u8string();           // error: well-formed in C++17
std::string s2 = p.generic_u8string();   // error
```

¶4 `u8string()` and `generic_u8string()` of `std::filesystem::path` now return `std::u8string` ([[fs.class.path]]). When you need a `std::string`, use `p.string()` (native encoding), or convert explicitly.

## Removed deprecated features [diff.cpp17.depr] {#diff.cpp17.depr}

C++20 removes a batch of library facilities deprecated in C++17. libc++ gives `-Wdeprecated-declarations` warnings for them under `-std=c++17`, and reports the names as nonexistent under `-std=c++20`.

¶1 `uncaught_exception()` is removed. Its meaning was unclear when several exceptions were active at once, and it has been superseded by `uncaught_exceptions()`, which returns a count. To find out in a destructor whether destruction is due to stack unwinding, the correct approach is to record `uncaught_exceptions()` at construction and compare in the destructor.

¶2 The adaptable function conventions are removed: the nested types `result_type`, `argument_type`, `first_argument_type` and `second_argument_type` in standard library classes, as well as `not1`, `not2`, `unary_negate` and `binary_negate`. These conventions could only describe unary and binary functions and did not extend to the general case; they have been superseded by `decltype`, `std::bind` and `std::not_fn`.

¶3 The redundant members of `std::allocator` are removed: `pointer`, `const_pointer`, `reference`, `const_reference`, `rebind`, `address`, `construct`, `destroy`, `max_size`, and `allocate` with a hint argument. They encouraged user containers to use the members of `std::allocator` directly instead of going through `std::allocator_traits`. When rewriting, always go through `std::allocator_traits<A>`, for example `traits::construct(a, p, args...)` and `traits::rebind_alloc<U>`.

¶4 `raw_storage_iterator` is removed. It encouraged the use of algorithms that might throw, but did not return the number of elements successfully constructed, so on an exception there was no way to destroy the part already constructed. Use algorithms such as `std::uninitialized_copy`, which clean up themselves on an exception.

¶5 `get_temporary_buffer` and `return_temporary_buffer` are removed. They were meant to provide efficient allocation for small memory requests, but there was no evidence they actually did, and users often had to write their own exception-safe wrappers.

¶6 `shared_ptr::unique()` is removed. With multiple threads and with `weak_ptr` in play, its result is unreliable. `use_count()` is just as unreliable, but its contract is clearer and it has a clear use in single-threaded code, so it stays.

¶7 The type traits `is_literal_type`, `is_literal_type_v`, `result_of` and `result_of_t` are removed ([[depr.meta.types]]). `is_literal_type` cannot tell you which member functions of a type are `constexpr`, so it was nearly useless; the syntax of `result_of<F(Args...)>` was surprising and did not directly support function types. Rewrite `result_of_t<F(Args...)>` as `invoke_result_t<F, Args...>`.

## Summary

| Entry | Fate of old code | Clang 23 / libc++ |
|---|---|---|
| lines starting with `module` or `import` | changed meaning | implemented |
| new keywords | ill-formed | implemented, `-Wc++20-compat` warns in advance |
| `<=>` token | ill-formed | implemented, `-Wc++20-compat` warns in advance |
| `u8` literals become `char8_t` | ill-formed | implemented |
| pseudo-destructor ends lifetime | later reads are UB | visible in constant evaluation |
| release sequences | data race | no diagnostic |
| implicit capture | closure may get larger | implemented, same in C++17 mode |
| unnamed class named by a typedef | ill-formed | warning only |
| default arguments across translation units | IFNDR | no diagnostic |
| definition of aggregate | ill-formed or changed meaning | implemented |
| pointer to `bool` narrowing | ill-formed | implemented, same in C++17 mode |
| `explicit (S)` | ill-formed | implemented |
| constructor name `A<T>` | ill-formed | not implemented |
| wider implicit move | ill-formed or behavior change | implemented, same in C++17 mode |
| reversed `==` candidates | ambiguity or a different function called | implemented, ambiguity only warns |
| `f < a` | ill-formed | implemented |
| `throw()` | ill-formed | not implemented |
| the four iostream and filesystem entries | ill-formed | implemented |
| removal of the empty C headers | ill-formed | libc++ still provides them |
| removed deprecated features | ill-formed | removed |
