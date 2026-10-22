---
title: Designing and evolving APIs
summary: "How to design C++ interfaces that are hard to misuse and can evolve: parameter and return types that express ownership and nullability, const and ref-qualifiers, making illegal states unrepresentable, nodiscard, deprecated and noexcept as part of the contract, the overload-set and ADL risks library authors face, and changing an interface without breaking users, giving users feature-test macros, and documenting preconditions."
group: Engineering practice
tags: API, interface design, compatibility, noexcept, nodiscard, deprecated, feature testing, engineering practice
updated: 2026-10-19
---

!!! tldr
    - Parameter types are documentation: `const T&` is a read-only borrow that cannot be null, `T*` is a borrow that can be null, `unique_ptr<T>` by value takes ownership, and `span` and `string_view` borrow a range of data. Pick the right type and misuse becomes a compile error.
    - A plain value, `optional` and `expected` express, respectively, "always has a result", "may have no result" and "may fail". Don't return owning raw pointers; when returning a reference to internal data, use ref-qualifiers to refuse calls on temporaries.
    - `[[nodiscard]]`, `[[deprecated("...")]]` and `= delete("...")` hand usage rules to the compiler to check. Since C++17 `noexcept` is part of the function type: adding it is easy, removing it breaks users.
    - A library author who adds one generic function template to the namespace of a user-visible type can silently change which function user code calls, via ADL. Use function objects for generic operations and hidden friends for operators.
    - Source compatibility and binary compatibility are different things. Adding a default argument and adding an overload break different things; removal should go through a release with an explanatory `[[deprecated]]`; new features should come with a macro users can `#if` on.

## An interface that is easy to misuse

```cpp
void open(const char* path, bool write, bool create);
Widget* make_widget();
const std::string& Person::name() const;
```

All three declarations compile, and all three admit calls that look normal. In `open("f", true, false)` you can't tell which `bool` is which, and swapping them still compiles. Who must `delete` the pointer returned by `make_widget()` is only in the documentation. `load().name()` returns a reference to a member of a temporary, which dangles once the expression ends.

The job of **API design** is to make correct use easy to write, and incorrect use impossible to write, or at least warned about. C++'s type system, attributes and overloading rules provide most of the tools. This page goes through the parts of a call one at a time: parameters, return values, qualifiers on member functions, attributes, and finally how to change an interface after it has shipped.

Binary-level conventions (layout, vtables, symbol visibility) are covered in [[toolchain/library-boundaries]]; choosing an error-reporting mechanism is covered in [[toolchain/error-handling-strategy]].

## Parameter types express ownership and nullability

A parameter answers three questions: does the function take ownership of the object, does it modify the object, and can the caller pass "no object". The table gives the conventional meaning of the common forms.

| Parameter | Meaning | Nullable? | Typical call |
|---|---|---|---|
| `T` (by value) | The function gets its own copy; for movable types also used for "take and store" | N/A | `f(x)`, `f(std::move(x))` |
| `const T&` | Read-only borrow, not used after the function returns | No | `f(x)` |
| `T&` | Writable borrow; the function modifies the caller's object | No | `f(x)` |
| `const T*`, `T*` | Borrow; `nullptr` means no object | Yes | `f(&x)`, `f(nullptr)` |
| `T&&` (non-template) | Accepts only rvalues; the function may move resources out | No | `f(std::move(x))` |
| `std::unique_ptr<T>` (by value) | Takes ownership | Yes | `f(std::move(p))` |
| `std::shared_ptr<T>` (by value) | Stores a share of ownership | Yes | `f(p)` |
| `std::span<const T>`, `std::span<T>` | Borrows a contiguous range of elements, read-only or writable | Can be an empty range | `f(vec)`, `f(arr)` |
| `std::string_view` | Borrows a range of characters, not guaranteed to be null-terminated | Can be an empty string | `f("lit")`, `f(str)` |
| `std::optional<T>` (by value) | Optional input; the function gets a copy | Yes (`std::nullopt`) | `f(5)`, `f(std::nullopt)` |
| `std::optional<const T&>` {{c++26}} | Optional read-only borrow | Yes | `f(x)`, `f(std::nullopt)` |

The details and reasons for each way of passing smart pointers are in [[topics/ownership-and-smart-pointers]]. One point bears repeating here: a function that only wants to use an object should take `T&` or `T*`, not a smart pointer; otherwise objects on the stack and objects held by some other owner can't be passed in.

With the right types, several common mistakes become compile errors:

```cpp title="params.cpp"
#include <memory>
#include <span>
#include <string>
#include <string_view>

struct Widget { int id; };

void inspect(const Widget& w);               // read-only borrow, cannot be null
void adopt(std::unique_ptr<Widget> w);       // takes ownership
void sum(std::span<const int> xs);           // borrows a contiguous range
void greet(std::string_view name);           // borrows a character sequence

void use() {
  auto p = std::make_unique<Widget>();
  inspect(nullptr);    // error: a reference cannot be null
  adopt(p);            // error: ownership must be handed over explicitly
  adopt(std::move(p)); // OK
  int a[] = {1, 2, 3};
  sum(a);              // OK
  std::string_view sv = std::string("temp");   // dangles
  greet(sv);
}
```

Diagnostics from Clang 23 with `-Wall -Wextra -pedantic` (source lines omitted):

```text
params.cpp:15:3: error: no matching function for call to 'inspect'
params.cpp:8:6: note: candidate function not viable: no known conversion from 'std::nullptr_t' to 'const Widget' for 1st argument
params.cpp:16:9: error: call to implicitly-deleted copy constructor of 'std::unique_ptr<Widget>'
params.cpp:20:25: warning: object backing the pointer will be destroyed at the end of the full-expression [-Wdangling-gsl]
```

The error on `adopt(p)` shows why taking ownership should accept `unique_ptr` by value: the call site has to spell out `std::move`, and a reader can see at a glance that `p` is empty afterwards.

The common risk of borrowing types (references, pointers, `span`, `string_view`) is dangling: the function stores what it borrowed, and the caller's object dies first. Hence a companion convention: a function that takes a borrow doesn't keep using it after it returns; if it needs to store it, it takes an owning type by value (`std::string`, `std::vector<T>`). The ways to dangle and how far compilers can diagnose them are covered in [[topics/dangling-references]].

!!! pitfall "`string_view` is not a C string"
    The character sequence a `std::string_view` refers to is not necessarily terminated by `'\0'`. Passing `sv.data()` to C functions that need a null terminator, such as `fopen` or `strlen`, may read past the range. For functions that call C interfaces underneath, make the parameter `const std::string&` or `const char*`.

!!! note "`T&&` versus by value"
    A non-template `T&&` parameter forces callers to write `std::move` or pass a temporary, which is unfriendly to callers that just want a copy made. For types that are cheap to move, such as `std::string` and `std::vector`, the recommended form is "take by value, then move into the member": a caller passing an lvalue pays one copy, a caller passing an rvalue only a move, and the function is written once. In a template, `T&&` is a forwarding reference and means something entirely different ([[g:forwarding-reference]]).

## Return types

| Return type | Meaning |
|---|---|
| `T` | Always produces a result, owned by the caller |
| `std::optional<T>` | There may be no result, and that is not an error (for example, a lookup) |
| `std::expected<T, E>` | May fail, and carries the reason back on failure |
| `std::unique_ptr<T>` | Returns ownership of a new object; used when polymorphism or a stable address is needed |
| `const T&`, `std::string_view`, `std::span` | Lends out internal data, valid only as long as the object lives |
| `std::optional<const T&>` {{c++26}} | May lend something out, or may not |

Choosing between `optional` and `expected`, and using `expected` across module boundaries, are covered in [[toolchain/error-handling-strategy]].

The libc++ used in our tests already implements `std::optional<T&>` (`__cpp_lib_optional` is `202506`, [[P2988]]). `sizeof(std::optional<const Config&>)` is 8 on our test machine, the size of one pointer: it is in effect a nullable pointer with explicit semantics.

### Don't return owning raw pointers

```cpp run title="owning.cpp" ok
#include <cstdio>
#include <memory>

struct Conn { int fd = 3; };

Conn* open_raw() { return new Conn; }              // who deletes this?
std::unique_ptr<Conn> open() { return std::make_unique<Conn>(); }

int main() {
  int fd1 = open_raw()->fd;     // leak: nobody owns this object
  int fd2 = open()->fd;         // the temporary unique_ptr frees it at the end of the full-expression
  std::printf("%d %d\n", fd1, fd2);
}
```

A memory leak is not UB, and the program is well-formed, but the first call leaks. Built with `-fsanitize=address` and run with `ASAN_OPTIONS=detect_leaks=1`, LeakSanitizer reports `Direct leak of 4 byte(s) in 1 object(s)` allocated in `open_raw()`. The same expression with a `unique_ptr` return doesn't leak, because ownership lands on a temporary that is responsible for freeing it.

When a library must return a raw pointer through a C interface, it should provide a matching destroy function; see [[toolchain/library-boundaries]].

## const and ref-qualifiers

### const member functions

A `const` member function promises not to modify the object's observable state, and it can be called on `const` objects and through `const T&`. For overload resolution, a member function has an implicit object parameter: for a member function without cv-qualifiers it is `X&`, for a `const` member function it is `const X&` ([[over.match.funcs.general#4]]). Overloading on `const` is therefore overloading on the type of the object parameter; this is how `std::vector::operator[]` provides both a read-only and a writable version.

The recommended practice is to write every member function as `const` first and remove it only when modification is really needed. A function that should be `const` but isn't marked is unusable for every caller that only has a `const T&`, while adding `const` later breaks no caller.

### Accessors that return internal references

```cpp run title="refq.cpp" ub
#include <cstdio>
#include <string>
#include <utility>

class Person {
  std::string name_;
public:
  explicit Person(std::string n) : name_(std::move(n)) {}
  const std::string& name() const { return name_; }
};

Person load() { return Person("a fairly long name, no SSO"); }

int main() {
  const std::string& n = load().name();   // the temporary Person is already destroyed
  std::printf("%zu\n", n.size());
}
```

The temporary returned by `load()` is destroyed at the end of the full-expression, and `n` refers to a member of an object that no longer exists. Clang 23 with `-Wall -Wextra` gives no warning at all for this code; under `-fsanitize=address` it reports `stack-use-after-scope` at run time.

A ref-qualifier distinguishes member functions by whether the object is an lvalue or an rvalue: the version with `&` can only be called on lvalues, the version with `&&` only on rvalues ([[over.match.funcs.general#4]]). The rvalue version can move the member out and return a value instead of a reference:

```cpp run title="refq2.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

class Person {
  std::string name_;
public:
  explicit Person(std::string n) : name_(std::move(n)) {}
  const std::string& name() const& { return name_; }
  std::string name() && { return std::move(name_); }
};

Person load() { return Person("a fairly long name, no SSO"); }

int main() {
  Person p = load();
  const std::string& a = p.name();        // lvalue: returns a reference
  const std::string& b = load().name();   // rvalue: returns a value, lifetime extended
  std::printf("%zu %zu\n", a.size(), b.size());
}
```

It prints `26 26` in our tests, with no ASan report. `b` binds to the temporary `std::string` returned by `name() &&`, and that temporary's lifetime is extended to the end of `b`'s scope.

When returning a view such as `string_view` or `span`, there is nothing to extend, and the rvalue version can simply be deleted:

```cpp title="view.cpp" error
#include <string>
#include <string_view>

class Person {
  std::string name_;
public:
  std::string_view view() const& { return name_; }
  std::string_view view() const&& = delete("would dangle");
};
Person load();

void use(const Person& p) {
  std::string_view a = p.view();        // OK
  std::string_view b = load().view();   // error: call to a deleted function
}
```

```text
view.cpp:14:31: error: call to deleted member function 'view': would dangle
```

`= delete("reason")` is C++26 syntax ([[dcl.fct.def.delete#2]], [[P2573R2]]); Clang 23 already supports it, and the diagnostic includes the reason. The cost of deleting the rvalue version is that perfectly safe uses such as `print(load().view())` are also rejected, so it suits interfaces whose views are likely to be stored. Another option is Clang's `[[clang::lifetimebound]]`: adding it to `name()` in `refq.cpp`, `const std::string& n = load().name();` gets a `-Wdangling` warning in our tests, while using the result within the full-expression is unaffected. See [[topics/dangling-references]].

!!! pitfall "Ref-qualified and unqualified overloads can't be mixed"
    Member functions with the same name and parameters can't be one with a ref-qualifier and one without: `int f() const;` and `int f() const&&;` are treated as redeclarations of the same function ([[basic.scope.scope#3.1]]), and Clang 23 reports `class member cannot be redeclared`. To distinguish by ref-qualifier, write it on both versions, for example `const&` and `const&&`.

How builder method chains use ref-qualifiers (and C++23 explicit object parameters) is covered in [[patterns/named-parameters]].

## Make illegal states unrepresentable

### Types instead of bool and bare integers

```cpp title="states.cpp" error
#include <chrono>

enum class Mode { read, write };
enum class Create : bool { no, yes };

void open(const char* path, Mode m, Create c);

void use() {
  open("f", Mode::write, Create::yes);   // OK
  open("f", Create::yes, Mode::write);   // error: wrong order
  open("f", 1, true);                    // error: no implicit conversion
}
```

```text
states.cpp:10:3: error: no matching function for call to 'open'
states.cpp:6:6: note: candidate function not viable: no known conversion from 'Create' to 'Mode' for 2nd argument
states.cpp:11:3: error: no matching function for call to 'open'
states.cpp:6:6: note: candidate function not viable: no known conversion from 'int' to 'Mode' for 2nd argument
```

A scoped enumeration (`enum class`, [[g:scoped-enumeration]]) doesn't convert implicitly to an integer, can't be implicitly converted from one, and two different enumerations certainly can't be exchanged. The same idea extends to numbers: wrap meters and seconds, or user IDs and order IDs, in distinct types, and passing arguments in the wrong order becomes a compile error. How to do it and when it is zero-cost is covered in [[patterns/strong-types]]. When there are many parameters, an options aggregate with designated initializers lets the call site spell out the parameter names; see [[patterns/named-parameters]].

`std::chrono::duration` is an example from the standard library: a function taking `std::chrono::milliseconds` doesn't accept `50`, because the constructor of `duration` from an integer is `explicit`; passing `2s` works, because converting seconds to milliseconds is lossless.

### Deleting unwanted conversions

Sometimes a parameter must be a fundamental type, but you don't want to accept arguments that got there by implicit conversion:

```cpp title="del.cpp" error
void set_percent(int p);
template <class T>
void set_percent(T) = delete("set_percent takes exactly int");

void use(double ratio, short s) {
  set_percent(ratio * 100);   // error: otherwise double -> int silently truncates
  set_percent(s);             // error: short -> int is lossless, but also rejected
  set_percent(42);            // OK
}
```

Without the deleted template, Clang 23 with `-Wall -Wextra -pedantic` gives no warning for either of the first two calls. With it, the template deduces an exact match for `double` and `short`, which beats `set_percent(int)` with its conversion; the template is selected, it is a deleted function, and so the program is ill-formed ([[dcl.fct.def.delete#2]]). For an `int` argument the two are equally good and the non-template wins. The diagnostic carries the reason:

```text
del.cpp:6:3: error: call to deleted function 'set_percent': set_percent takes exactly int
del.cpp:3:6: note: candidate function [with T = double] has been explicitly deleted
```

### Establishing invariants at construction

When the valid range of a value is narrower than its type (a port number is an `int` from 1 to 65535), the check can go into the construction of a class: make the constructor `explicit` and throw on failure, or make the constructor private and provide only a factory function returning `std::expected<Port, Error>`. From then on, no function taking a `Port` needs to check again. The full version of this example is in [[toolchain/error-handling-strategy]].

## nodiscard and deprecated

### `[[nodiscard]]`

`[[nodiscard]]` can be applied to functions, constructors and types. When the result of a nodiscard call is discarded, the standard recommends that implementations issue a warning and include the attribute's string in it ([[dcl.attr.nodiscard#4]]). The effect of marking a type, and the fact that libc++'s `std::expected` is not a nodiscard type, are covered in [[toolchain/error-handling-strategy]]. This section is about which functions deserve it.

```cpp title="attrs.cpp"
#include <memory>
#include <mutex>
#include <vector>

class Lock {
public:
  [[nodiscard("the lock is released immediately")]]
  explicit Lock(std::mutex& m);
  ~Lock();
};

[[nodiscard]] int compute(int x);

void use(std::mutex& m, std::vector<int>& v, std::unique_ptr<int>& p) {
  Lock{m};         // destroyed right after construction
  compute(1);
  v.empty();       // meant to clear, actually just a query
  p.release();     // leak
}
```

```text
attrs.cpp:15:3: warning: ignoring temporary created by a constructor declared with 'nodiscard' attribute: the lock is released immediately [-Wunused-value]
attrs.cpp:16:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
attrs.cpp:17:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
```

The warning for `v.empty()` comes from libc++, which marks `vector::empty` as `[[nodiscard]]`. `p.release()` gets no warning in our tests: this version of libc++ doesn't put the attribute on `unique_ptr::release`, even though discarding its result always leaks.

Cases where `[[nodiscard]]` is recommended, all because discarding the result is almost certainly a bug:

- functions with no effect other than the return value, such as `empty()`, `size()` and pure computations;
- functions that return a resource or ownership, such as `release()` and factory functions;
- functions that report failure through the return value;
- constructors that acquire a resource, such as locks and scope guards ([[P1771R1]]).

The form with a string was added in C++20 ([[P1301R4]]). A string telling the caller what to do is more useful than a bare warning.

### `[[deprecated]]`

`[[deprecated]]` marks names or entities that can still be used but whose use is discouraged. It can be applied to classes, type aliases, variables, non-static data members, functions, namespaces, enumerations, enumerators, concepts and template specializations ([[dcl.attr.deprecated#2]]); implementations should issue a diagnostic when the program refers to one, including the attribute's string ([[dcl.attr.deprecated#4]]).

```cpp title="dep.cpp"
namespace geo {
struct Vector2 { double x, y; };
using Vec [[deprecated("renamed to geo::Vector2")]] = Vector2;

enum class Unit { meter, metre [[deprecated("use Unit::meter")]] = meter };

double length(const Vector2& v);
[[deprecated("use length(); removed in 3.0")]]
inline double norm(const Vector2& v) { return length(v); }
}

double user(geo::Vec v, geo::Unit u) {
  if (u == geo::Unit::metre) return geo::norm(v);
  return 0;
}
```

```text
dep.cpp:12:18: warning: 'Vec' is deprecated: renamed to geo::Vector2 [-Wdeprecated-declarations]
dep.cpp:13:23: warning: 'metre' is deprecated: use Unit::meter [-Wdeprecated-declarations]
dep.cpp:13:42: warning: 'norm' is deprecated: use length(); removed in 3.0 [-Wdeprecated-declarations]
```

These three forms cover the most common evolution steps: when renaming a type, leave a deprecated alias; when renaming an enumerator, leave a deprecated enumerator with the same value; when replacing a function, have the old one forward to the new one. State the replacement and the version in which removal is planned in the message.

`[[deprecated]]` can be added on a later redeclaration ([[dcl.attr.deprecated#3]]), so a library can also deprecate old interfaces centrally in a separate header.

!!! pitfall "Users' `-Werror`"
    Users who build with `-Werror` will see their build fail outright when they upgrade to a version that newly deprecates some interfaces: the example above with `-Wall -Werror` gives 3 errors in our tests. That isn't the library's fault, but it makes users postpone upgrading. Remind users in the release notes that `-Wno-error=deprecated-declarations` keeps these diagnostics as warnings; with it added, the three diagnostics go back to being warnings and compilation succeeds.

## noexcept is part of the contract

### The promise, and who relies on it

`noexcept` declares that a function does not exit via an exception. It is not a check: if an exception really does leave a `noexcept` function, `std::terminate` is called ([[topics/exception-safety]]). Callers can query this promise at compile time with `noexcept(expr)` and choose an algorithm accordingly: when `std::vector` grows, it moves the elements only if their move constructor doesn't throw, and copies them otherwise.

So `noexcept` is part of the interface, and callers' code comes to depend on it just as on the return type.

### Part of the function type since C++17

A function type consists of the return type, the parameter-type-list, the ref-qualifier, the cv-qualifiers and the exception specification, but not default arguments ([[dcl.fct#13]]). The exception specification became part of the type system in C++17 ([[P0012R1]]).

```cpp title="nx.cpp" error
void may_throw();
void wont_throw() noexcept;

void (*p1)() = wont_throw;            // OK: noexcept can be dropped
void (*p2)() noexcept = may_throw;    // error: noexcept can't be added out of thin air
static_assert(!__is_same(decltype(may_throw), decltype(wont_throw)));

void h();
void h() noexcept;                    // error: can't overload on noexcept

struct Base { virtual void run() noexcept; };
struct Derived : Base { void run() override; };   // error
```

```text
nx.cpp:5:8: error: cannot initialize a variable of type 'void (*)() noexcept' with an lvalue of type 'void ()': different exception specifications
nx.cpp:9:6: error: exception specification in declaration does not match previous declaration
nx.cpp:12:30: error: exception specification of overriding function is more lax than base version
```

The rules, one by one:

- A pointer to a `noexcept` function can be converted to an ordinary function pointer, but not the other way round ([[conv.fctptr#1]]).
- Deciding whether two declarations are overloads compares the parameter-type-lists and so on, but not exception specifications ([[basic.scope.scope#4]]). So `h()` and `h() noexcept` are two declarations of the same function, and the mismatched exception specifications are an error ([[except.spec#4]]).
- If a base class's virtual function is `noexcept`, any function overriding it must be too ([[except.spec#5]]).

Compiling the same file with `-std=c++14` makes the `static_assert` fail: in C++14 the two functions have the same type. In Clang 23, `__cpp_noexcept_function_type` is `201510`.

### Adding and removing

A function's own mangled name doesn't contain its exception specification. On our test machine the symbol for `void f() noexcept {}` is `__Z1fv`, the same as without `noexcept`, so adding `noexcept` to a non-template function doesn't change its exported symbol. But when a parameter has function-pointer type, `noexcept` appears in the parameter type and the mangled names differ: `take(void (*)() noexcept)` is `__Z4takePDoFvvE`, `take(void (*)())` is `__Z4takePFvvE`, and the two can coexist. The mangling rules are in [[toolchain/name-mangling]].

At the source level, the risks in the two directions are not symmetric:

- **Adding** `noexcept` is almost always compatible. Users' existing `void (*)()` pointers can still point to the function. Only code that depends on the exact type is affected, for example `decltype(&f)` now includes `noexcept`.
- **Removing** `noexcept` breaks users: a pointer of type `void (*)() noexcept` can no longer point to it, `static_assert(noexcept(f()))` fails, and derived classes overriding it aren't affected but the base class's constraint is gone. Performance is the more insidious part: once a type's move constructor loses `noexcept`, `std::vector<T>` switches to copying when it grows, without any diagnostic.

So `noexcept` should only be added to functions that are certain never to throw in the future either. The standard library follows a conservative convention: functions with preconditions (narrow contracts) are usually not declared `noexcept` even if they don't throw in normal use, so that a debugging implementation can throw an exception when a precondition is violated, which makes testing easier ([[N3279]], often called the Lakos rule; see [[description]]).

!!! tip "Recommendation"
    Move construction, move assignment, `swap` and destructors should be `noexcept`: they affect the behavior of standard containers, and they can almost always be written not to throw. Mark other functions only when not throwing is a promise of the interface, not merely a property the current implementation happens to have.

## Overload sets and ADL: a risk for library authors

### Adding a template hijacks a user's call

Argument-dependent lookup (ADL) looks up function names in the namespaces of the argument types ([[basic.lookup.argdep]]; see [[topics/name-lookup-and-customization]]). For a library author this means that every function name in the library's namespace takes part in every unqualified call the user makes on a library type.

```cpp run title="adl.cpp" ok
#include <cstdio>

namespace geo {
struct Point { int x, y; };
#ifdef V2
template <class T>            // generic utility added in v2
void dump(T&) { std::puts("geo::dump"); }
#endif
}

// user code, written in the v1 days
void dump(const geo::Point& p) { std::printf("user dump %d,%d\n", p.x, p.y); }

int main() {
  geo::Point p{1, 2};
  dump(p);
}
```

Compiled against v1 it prints `user dump 1,2`; recompiled with `-DV2` it prints `geo::dump`, with no diagnostic. The v2 template enters the candidate set through ADL, `T` is deduced as `geo::Point`, and binding the parameter `geo::Point&` to a non-`const` lvalue argument is better than the user's `const geo::Point&` (among reference bindings, the less cv-qualified one wins), so the template is chosen. The library only added a function, and the user's program changed behavior.

### Function objects don't take part in ADL

ADL only finds declarations of functions and function templates ([[basic.lookup.argdep#4]]); if unqualified lookup finds a variable, ADL isn't done at all ([[basic.lookup.argdep#1]]). So if a generic operation is written as a function object, other people's unqualified calls can't find it by accident:

```cpp run title="adl2.cpp" ok
#include <cstdio>

namespace geo {
struct Point { int x, y; };
struct dump_fn {
  template <class T>
  void operator()(T&) const { std::puts("geo::dump"); }
};
inline constexpr dump_fn dump{};   // an object, not a function: ADL can't find it
}

void dump(const geo::Point& p) { std::printf("user dump %d,%d\n", p.x, p.y); }

int main() {
  geo::Point p{1, 2};
  dump(p);         // the user's function
  geo::dump(p);    // the library's version, used explicitly
}
```

It prints `user dump 1,2` and `geo::dump`. The C++20 `std::ranges` algorithms are implemented this way ([[g:algorithm-function-object]]).

Rules a library author can follow:

1. Don't put unconstrained function templates with common names in the namespace of your own types. If you really need one, constrain it with a concept or write it as a function object.
2. Write operators and functions such as `swap` that only make sense for this class as hidden friends ([[g:hidden-friend]]): a friend function defined only inside the class can only be found by ADL, enters the candidate set only when an argument is of this class, and doesn't show up in other types' overload sets or error messages.
3. When the library calls its own helpers internally, use qualified names (`detail::helper(x)`); otherwise a same-named function in the namespace of the user's type will be found by ADL.
4. When users need to customize behavior, specify the customization mechanism explicitly: a function looked up by ADL with a name unlikely to collide, a trait that can be specialized, or a customization point object. The trade-offs between these designs are in [[topics/name-lookup-and-customization]].

## Evolution: changing an interface without breaking users

### Two kinds of compatibility

**Source compatibility** means that the user's code, unmodified and recompiled against the new headers, is still well-formed and means the same thing. **Binary compatibility** (ABI compatibility) means that the user's program, not recompiled, still runs correctly with the new version of the library. Neither implies the other: adding a data member to a `struct` is usually source-compatible but breaks the ABI; changing a parameter from `const std::string&` to `std::string_view` is source-compatible for most callers, but the mangled name changes, which also breaks the ABI. The ways to break an ABI and how to check for them are in [[toolchain/library-boundaries]]; this section is about the source level.

### Default argument or overload?

Suppose v2 needs to add a timeout parameter to `connect`:

```cpp title="evo.cpp"
namespace net {
#if VER == 1
void connect(const char* host);
#elif VER == 2   // option A: add a parameter with a default argument
void connect(const char* host, int timeout_ms = 1000);
#else            // option B: add an overload
void connect(const char* host);
void connect(const char* host, int timeout_ms);
#endif
}

void user() {
  net::connect("example.org");                   // compiles with all three versions
  void (*fp)(const char*) = &net::connect;       // error in A
  auto ap = &net::connect;                       // error in B
  (void)fp; (void)ap;
}
```

```text
VER=2: error: cannot initialize a variable of type 'void (*)(const char *)' with an rvalue of type 'void (*)(const char *, int)': different number of parameters (1 vs 2)
VER=3: error: variable 'ap' with type 'auto' has incompatible initializer of type '<overloaded function type>'
```

Both options are compatible for direct calls, and they break different things:

| | Option A: default argument | Option B: overload |
|---|---|---|
| Direct calls | Compatible | Compatible |
| Taking the address as `void (*)(const char*)` | Error, the function type changed | Compatible, the overload is selected by the target type |
| `auto p = &net::connect` | Compatible | Error, the overload set has no unique type |
| The old exported symbol | Gone: on our test machine `__ZN3net7connectEPKc` becomes `__ZN3net7connectEPKci` | Kept |
| Can the default change later? | Only for recompiled callers (default arguments are evaluated at the call site, [[dcl.fct.default#9]]) | The default lives inside the library and can change |

For a library shipped in binary form, option B is better: the old symbol remains, and the default stays inside the library. Option A has fewer declarations, which suits header-only libraries used only as source.

The standard library defuses the address-taking risk by rule: unless the standard designates a function as addressable, the behavior of a program that takes the address of a standard library function is unspecified, and the program may be ill-formed ([[namespace.std#6]]). That leaves the standard library free to add overloads and default arguments. A library can declare the same rule in its documentation.

### Other common changes

| Change | Source-compatible? |
|---|---|
| Adding an enumerator to an enumeration | Compiles, but users' `switch` on it gets a `-Wswitch` warning: `enumeration value 'fatal' not handled in switch` in our tests; users with `-Werror` fail to build |
| Changing a parameter from `const std::string&` to `std::string_view` | Most calls are compatible; types that only convert implicitly to `std::string` can no longer be passed, and Clang 23 reports `no known conversion from 'Name' to 'std::string_view'` |
| Adding `noexcept` to a function | Compatible (see the previous section) |
| Removing `noexcept` | Incompatible |
| Adding a data member at the end of an aggregate | Positional or designated initialization still compiles, but with `-Wextra` Clang 23 warns `-Wmissing-field-initializers` or `-Wmissing-designated-field-initializers` where the new member isn't initialized; the number of structured bindings changes, which is incompatible |
| Adding a missing `const` to a member function | Compatible |
| Adding a function or function template to the library namespace | May change which function a user call resolves to via ADL; see the previous section |

### Deprecate first, then remove

To remove or rename a public name, the recommended process has three steps, each at least one release apart:

1. Add the new interface and have the old one forward to it; the two coexist.
2. Mark the old interface `[[deprecated("use X; removed in N")]]`, stating the replacement and the removal version.
3. Remove the old interface in the stated version.

Step 2 gives users a message at compile time, on the line that uses the old interface, instead of a `no member named` error after the upgrade that sends them to the release notes.

### Inline namespaces as version numbers

Put the public interface in an inline namespace, `namespace geo { inline namespace v2 { ... } }`. Users still write `geo::f`, but the mangled names carry `v2` ([[namespace.def#6]]). For an incompatible change, switch to a different inline namespace, and old binaries fail at link or load time instead of silently reading the wrong memory. The full experiment, the trap of having to use qualified names for definitions in implementation files, and libc++'s `std::__1` are covered in [[toolchain/library-boundaries]].

It has one more use at the source level: the old version's namespace stops being inline but is kept, and users who need the old behavior can write `geo::v1::f` explicitly.

## Feature-test macros

### How users detect the standard library

```cpp run title="ftm.cpp" ok
#include <cstdio>
#include <version>

#if __has_include(<expected>)
#  include <expected>
#endif

int main() {
#ifdef __cpp_lib_expected
  std::printf("__cpp_lib_expected      %ld\n", (long)__cpp_lib_expected);
#endif
#ifdef __cpp_lib_function_ref
  std::puts("function_ref available");
#else
  std::puts("__cpp_lib_function_ref  undefined");
#endif
#ifdef __cpp_contracts
  std::puts("contracts available");
#else
  std::puts("__cpp_contracts         undefined");
#endif
}
```

With `-std=c++2c` on our test machine it prints `__cpp_lib_expected 202211`, and neither `__cpp_lib_function_ref` nor `__cpp_contracts` is defined; `<version>` defines 188 `__cpp_lib_` macros there.

The two kinds of test answer different questions. `__has_include(<expected>)` only says that the header can be found ([[cpp.cond#3]]). Compiled with `-std=c++20` in our tests, `__has_include(<expected>)` is true, but after including it, using `std::expected` gives `use of undeclared identifier 'std'`, because libc++ only declares it in C++23 and later modes. `__cpp_lib_expected` is defined in `<version>` and in the corresponding header ([[version.syn#2]]); its value is the year and month the feature was adopted, and it is what says the feature is available in the current mode. Language feature macros (`__cpp_deleted_function` and so on) are predefined by the compiler ([[cpp.predefined#1.2]]) and need no header.

So the recommended pattern is: `#include <version>` first, then test `__cpp_lib_*`; use `__has_include` to detect non-standard headers, or headers that may not be installed. `__has_include` can only appear in conditions such as `#if` ([[cpp.cond#7]]); writing it in an ordinary expression gives `'__has_include' must be used within a preprocessing directive` in Clang 23.

`__has_include` comes from C++17 ([[P0061R1]]); feature-test macros were written into the body of the standard only in C++20 ([[P0941R2]]).

### Defining macros for your own library

A library should give its users the same tools. A `version.h` typically contains:

```cpp title="geo/version.h"
#pragma once
#define GEO_VERSION_MAJOR 2
#define GEO_VERSION_MINOR 4
#define GEO_VERSION_PATCH 0
#define GEO_VERSION \
  (GEO_VERSION_MAJOR * 10000 + GEO_VERSION_MINOR * 100 + GEO_VERSION_PATCH)

#define GEO_HAS_SIMPLIFY 202609L   // year and month simplify() was added
```

Users write `#if defined(GEO_HAS_SIMPLIFY)` or `#if GEO_VERSION >= 20400` and can support both old and new versions of the library. Per-feature macros are more robust than version comparisons: a feature may be backported to an old maintenance branch, but the version number won't be. This header can be generated by the build system from the project version; see [[toolchain/cmake]].

Macro names should carry the library's own prefix. Don't imitate the standard with `__cpp_geo_simplify`: identifiers containing a double underscore are reserved for the implementation, and using them is IFNDR ([[lex.name#4.1]]).

## Documenting preconditions

A **precondition** is a condition the function assumes holds when it is called, and which the caller is responsible for ensuring. Violating a precondition is a bug in the caller; the function need not, and usually cannot, report it.

The standard library's specifications divide a function's requirements into several elements ([[structure.specifications#3]]): if *Constraints* are not satisfied, the function doesn't take part in overload resolution; if *Mandates* are not satisfied, the program is ill-formed; if *Preconditions* are not satisfied, the behavior is undefined; *Hardened preconditions* are guaranteed to be checked in a hardened implementation. The precise meanings of these terms are in [[description]]. A library's documentation can borrow the same classification, so users know which requirements the compiler guarantees and which they must guarantee themselves.

Don't write a condition as a precondition if a type can express it. `const T&` is better than "`p` must not be null", a `Port` type is better than "`port` must be between 1 and 65535", and `span` is better than "`n` must not exceed the length of the array `p` points to". Write the remaining conditions in the documentation, and check them with `assert` in debug builds.

C++26 allows preconditions and postconditions to be written on declarations ([[P2900R14]]):

```cpp title="contracts.cpp (C++26, not supported by Clang 23, not compiled)"
double sqrt_checked(double x)
  pre(x >= 0)
  post(r: r >= 0);
```

The precondition then becomes part of the declaration, visible to callers and tools, and whether it is checked is decided by the evaluation semantic chosen at build time. Clang 23 doesn't define `__cpp_contracts` and has no `<contracts>` header, so the example has not been verified. The semantics of contracts and their relation to `assert` and standard library hardening are covered in [[toolchain/error-handling-strategy]]; the design trade-offs and open questions in [[history/contracts]].

## Checklist

| Question | Recommendation |
|---|---|
| Do parameters express ownership and nullability? | Borrow with `T&`, `T*`, `span`, `string_view`; take ownership with an owning type by value |
| Return values | Value, `optional`, `expected`, `unique_ptr`; no owning raw pointers |
| Returning a reference or view of internal data | Distinguish lvalues and rvalues with ref-qualifiers, or use `[[clang::lifetimebound]]` |
| Boolean and integer parameters | Replace with `enum class` or strong types; reject unwanted conversions with `= delete` |
| Is discarding the result a bug? | If so, mark it `[[nodiscard("...")]]` |
| Move operations, `swap` | `noexcept` |
| Generic functions in the library namespace | Constrain them, or make them function objects; hidden friends for operators |
| Adding a parameter | When shipping binaries, use an overload, not a default argument |
| Removing or renaming | Old and new coexist, `[[deprecated("...")]]` for at least one release, then remove |
| How do users detect new features? | Provide prefixed version macros and feature macros |

## Questions

!!! question "1"
    In v1 of a library, `struct Buffer { Buffer(Buffer&&); };` has a move constructor without `noexcept`. v2 adds `noexcept` to it, with the body unchanged. If a user's program is not recompiled and is simply run with the v2 shared library, does the growth behavior of `std::vector<Buffer>` change? What about after recompiling?

<details markdown="1">
<summary>Answer</summary>

Without recompiling, it doesn't change. `vector` is a template; the decision between moving and copying (`std::move_if_noexcept`) was made when it was instantiated in the user's translation unit, and is compiled into the user's binary. The move constructor's own mangled name doesn't contain the exception specification, so the v2 library still exports the same symbol, loading succeeds, and the user's code keeps copying elements.

After recompiling, `noexcept(Buffer(std::declval<Buffer>()))` is true and growth switches to moving. This is an example of a change that is source-compatible and binary-compatible, but whose performance characteristics change on recompilation. The change in the other direction (removing `noexcept`) makes recompiled users fall back from moving to copying, with no diagnostic.
</details>

!!! question "2"
    In `adl2.cpp`, `geo::dump` was turned into a function object. What happens if the user writes `using namespace geo;` and then calls `dump(p)`?

<details markdown="1">
<summary>Answer</summary>

Unqualified lookup now finds the user's function `::dump` in the global namespace, and, through the using-directive, the variable `geo::dump` in `geo`. One is a function and the other a variable, so the lookup result is ambiguous and the program is ill-formed. A function object only prevents ADL from finding the library's name by accident; it can't protect against a user deliberately merging the two namespaces with a using-directive. This is one more reason not to write `using namespace` in headers.
</details>

!!! question "3"
    Why, after pairing `set_percent(int)` with `template <class T> void set_percent(T) = delete;`, does `set_percent(42)` still call the `int` version while `set_percent(42L)` is rejected?

<details markdown="1">
<summary>Answer</summary>

For `42` (an `int`), the template deduces `T = int`; both candidates are exact matches and the conversion sequences can't distinguish them, in which case a non-template function is better than a template specialization ([[over.match.best]]), so `set_percent(int)` is chosen. For `42L`, the template deduces `T = long`, an exact match, while `set_percent(int)` needs an integral conversion and ranks lower. The best candidate is the deleted template specialization, and referring to a deleted function makes the program ill-formed ([[dcl.fct.def.delete#2]]).
</details>
