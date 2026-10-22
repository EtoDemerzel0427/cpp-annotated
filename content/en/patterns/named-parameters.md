---
title: Named parameters and builders
summary: C++ has no named arguments. How to make a call like open("f", true, false, 4096) readable: enums instead of bool parameters, option aggregates with designated initializers, method chains returning *this by reference, ref-qualifiers and explicit object parameters for temporary builders, and a few traps of default arguments.
tags: idiom, designated initializers, aggregates, builder, method chaining, deducing this, default arguments
updated: 2026-10-19
---

!!! tldr
    - Positional arguments are distinguished only by order, and the compiler won't notice when two arguments of the same type are swapped. `bool` parameters are especially dangerous: pointers, integers and floating-point numbers all convert implicitly to `bool`.
    - C++20 designated initializers with an option aggregate let you write `open_file("f", {.create = true, .buffer = 4096})`: members not written take their default member initializers, and wrong order, narrowing and duplicates are compile errors. The price is that the option type must be an aggregate and cannot have constructors.
    - A builder's method chain returns `*this` by reference. Chaining on a temporary builder is safe up to the semicolon; binding the result of the chain to a reference dangles.
    - Overloading on the `&` / `&&` ref-qualifiers lets the chain on a temporary builder return by value, eliminating the dangling at its root. C++23's explicit object parameters (deducing this) merge the two overloads into one template and also let a derived builder's chain keep the derived type.
    - Default arguments are expanded at the caller, chosen by static type, and are not part of the function type. Default arguments of virtual functions and changing defaults in headers are two common traps.

## Unreadable calls

```cpp title="positional.cpp" run ok
#include <string_view>

void open_file(std::string_view /*path*/, bool /*create*/,
               bool /*truncate*/, bool /*append*/, int /*buffer*/) {}

int main() {
  open_file("a.log", true, false, true, 4096);  // which true is which?
  open_file("a.log", "create", 4096, true, 0);  // also compiles
}
```

The first call can only be understood next to the declaration. The second puts a string and an integer where `bool`s belong, and still compiles: the string literal decays to a pointer, which converts to `bool`; `4096` also converts to `bool`; `true` converts to `int`. By [[conv.bool#1]], arithmetic types, unscoped enumerations and pointers all convert to `bool`. Clang 23 with `-Wall -Wextra -pedantic` gives no warning for either line.

C++ has no named arguments, so the names have to go into types. There are several approaches, from light to heavy:

1. Replace `bool` with enumerations, and same-typed numbers with distinct strong types, so that a misplaced argument becomes a type error;
2. Collect a group of optional parameters into an option aggregate and fill it in by name with designated initializers;
3. Use a builder: an object dedicated to collecting parameters, with one member function per parameter, whose last step constructs the result and checks constraints between parameters.

## Let types check positions for you

```cpp title="enum-flags.cpp" error
#include <string_view>

enum class Create : bool { no, yes };
enum class Truncate : bool { no, yes };

void open_file(std::string_view path, Create, Truncate);

void t() {
  open_file("a.log", Create::yes, Truncate::no);  // OK
  open_file("a.log", Truncate::no, Create::yes);  // error: type mismatch
  open_file("a.log", true, false);                // error: bool does not implicitly convert to an enum
}
```

There are no implicit conversions between scoped enumerations (`enum class`) and integers: the integral promotions in [[dcl.enum#11]] apply only to unscoped enumerations, and the boolean conversions in [[conv.bool#1]] don't include them either. The call site must write `Create::yes`, and the reader no longer needs to look up the declaration. With `bool` as the underlying type, its size and calling convention are the same as `bool`'s.

The same approach works for numbers: in `resize(Width{800}, Height{600})` the two arguments have different types, so swapping them fails to compile. How to define such wrapper types, and how to avoid rewriting operators for each one, is covered in [[patterns/strong-types]].

This step only solves misplaced arguments. With many parameters, the caller still has to write each one in order, even if most take their default values.

## Option aggregates and designated initializers {{c++20}}

### The syntax

```cpp title="options.cpp" run ok
#include <cstdio>
#include <string_view>

struct OpenOptions {
  bool create = false;
  bool truncate = false;
  bool append = false;
  int buffer = 8192;
};

void open_file(std::string_view path, OpenOptions o = {}) {
  std::printf("%.*s create=%d truncate=%d append=%d buffer=%d\n",
              int(path.size()), path.data(),
              o.create, o.truncate, o.append, o.buffer);
}

int main() {
  open_file("a.log");
  open_file("b.log", {.create = true, .buffer = 4096});
  open_file("c.log", {.append = true});
}
```

It prints three lines; the `b.log` line is `create=1 truncate=0 append=0 buffer=4096`. The call site writes only the options it changes, the rest take their defaults, and it reads much like keyword arguments in other languages.

### Why this works

`{.create = true, .buffer = 4096}` is a **designated-initializer-list** ([[P0329R4]]), and each `.name = value` item is a designated-initializer-clause. As an argument, it copy-list-initializes the parameter `o`. Several rules combine:

- [[dcl.init.list#3]] bullet 1: if the list contains designated-initializer-clauses, the type being initialized must be an aggregate class, and aggregate initialization is performed.
- [[dcl.init.aggr#4]]: the designated members are the explicitly initialized elements, and ¶5.2.1 initializes each with the initializer in the corresponding clause.
- [[dcl.init.aggr#6]]: an element that is not explicitly initialized uses its default member initializer if it has one (¶6.1), and is otherwise copy-initialized from `{}` (¶6.2). That is why `truncate` and `append` are `false`.
- [[dcl.init.aggr#8]]: all elements are initialized in declaration order, and the side effects of one element are complete before the next.

An **aggregate** ([[g:aggregate]]) is an array, or a class with no user-declared constructors, no private or protected direct non-static data members, and no virtual functions or virtual bases ([[dcl.init.aggr#1]]). Default member initializers do not affect aggregate status, so an option type can have both default values and designated initialization.

### The rules at a glance

C++ adopted only a subset of C99 designated initializers. All the restrictions come from the same model: members are initialized in declaration order, each exactly once. The full analysis of the wording is in [[dcl.init.aggr]].

| Syntax | Result | Source |
|---|---|---|
| `{.buffer = 1, .create = true}`, order differs from declaration | ill-formed | [[dcl.init.list#3]] bullet 1 |
| `{true, .buffer = 1}`, mixing ordinary and designated clauses | ill-formed in C++20/23; the current draft allows ordinary clauses only for initializing bases | [[dcl.init.aggr#4]], [[P2287R5]] |
| `{.o.buffer = 1}`, nested designator | ill-formed; the grammar only has `. identifier` | [[dcl.init.general#1]] |
| `{.o = {.buffer = 1}}`, nested list | OK | [[dcl.init.aggr#5]] |
| `{.create = true, .create = false}`, duplicate | ill-formed | [[dcl.init.general#20]] |
| `{.buffer = 4096.5}` or `{.buffer = n}` with `n` a `long` | ill-formed: narrowing | [[dcl.init.aggr#5]] bullet 2.1 |
| The option type has a constructor, even `= default` | ill-formed: not an aggregate | [[dcl.init.aggr#1]], [[P1008R1]] |
| The option type has private data members | ill-formed: not an aggregate | [[dcl.init.aggr#1]] |

Clang 23 reports errors for narrowing, duplicates and non-aggregates, but accepts out-of-order designators, nested designators and mixing as C99 extensions, issuing only `-Wreorder-init-list` and `-Wc99-designator` warnings; they become errors only with `-pedantic-errors`. Portable code should treat these two warnings as errors.

The narrowing check deserves a remark. Ordinary copy-initialization `int x = 4096.5;` allows narrowing, but the `= value` form of a designated clause does not; that is a sentence ¶5.2.1 adds specifically. Numeric options therefore never get silently truncated.

### Common options in a base class

When several option groups share some fields, the natural idea is to put the common part in a base class:

```cpp
struct Common { int timeout = 30; int retries = 3; };
struct HttpOptions : Common { bool keep_alive = true; };

HttpOptions a{.timeout = 5, .keep_alive = false};          // ill-formed in C++20/23, OK in the draft
HttpOptions b{Common{.timeout = 5}, .keep_alive = false};  // ill-formed in C++20/23, OK in the draft
HttpOptions c{{.timeout = 5}, false};                      // OK: base initialized positionally
```

In C++20/23 a designator can only name the class's own direct members, and bases can only be initialized positionally, as in `c`. The current draft relaxes this per [[P2287R5]]: a designator may name a member of a base (`a`), and a base may first be initialized with an ordinary clause followed by designated clauses for the class's own members (`b`). At the time of writing, Clang 23 rejects `a` (field designator 'timeout' does not refer to any field) and gives only a C99 extension warning for `b`, so this code carries no verdict. For portability, use composition instead of inheritance: `struct HttpOptions { Common common; bool keep_alive = true; };`, written at the call site as `{.common = {.timeout = 5}}`.

### Required fields

Every member of an option aggregate has a default, so a caller who forgets one still compiles. If a field must be supplied by the caller, give it a type that cannot be initialized from `{}`:

```cpp title="required.cpp" run ok
#include <concepts>
#include <string>
#include <utility>

template<class T> struct Required {
  T value;
  template<class U> requires std::constructible_from<T, U>
  Required(U&& u) : value(std::forward<U>(u)) {}   // no default constructor
};

struct ConnectOptions {
  Required<std::string> host;
  int port = 443;
  bool tls = true;
};

void connect(ConnectOptions) {}

int main() {
  connect({.host = "example.org", .port = 8443});  // OK
  // connect({.port = 8443});  // error: host cannot be initialized from {}
}
```

When `.host` is omitted, by [[dcl.init.aggr#6]] bullet 2, `host` is copy-initialized from `{}`. `Required` is not an aggregate and has no default constructor, and the template constructor cannot deduce `U` from an empty list, so initialization fails and `ConnectOptions` cannot be initialized from this list. `ConnectOptions` itself is still an aggregate: the conditions only look at whether it has constructors itself, not its members.

The constructor is a template because getting from `"example.org"` to `Required<std::string>` takes two user-defined conversions (first to `std::string`, then to `Required`), and an implicit conversion sequence allows only one.

!!! impl "Warnings for omitted fields"
    Clang's `-Wmissing-designated-field-initializers` (included in `-Wextra`) warns about fields omitted from a designated list that have no default member initializer. It does not warn for fields with a default member initializer. So giving every field of an option type a default both expresses the intent and makes the warning appear only for real omissions.

### Interaction with overload resolution

When a designated list is an argument, [[over.ics.list#2]] says a conversion exists only if the parameter is an aggregate that can be aggregate-initialized from the list. The names in the designators therefore take part in overload resolution:

```cpp title="overload.cpp" error
struct A { int x, y; };
struct C { int x; int z; };
void h(A);
void h(C);

void t() {
  h({.y = 2});   // OK: only A has a member y
  h({.z = 2});   // OK: only C has a member z
  h({.x = 1});   // error: ambiguous
}
```

Order does not take part in this step. Note 1 in [[over.ics.list#2]] explains that the overload is chosen by names first, and only then is the order checked; a wrong order is an initialization failure, not a switch to another overload.

### Costs

An option aggregate is an ordinary value type, passed by value according to the platform ABI's rules for small structs. `OpenOptions` is 8 bytes (three `bool`s, one padding byte, one `int`), and both arm64 and cross-compiled x86-64 Linux pass it in a single register in our tests:

<div class="compare" markdown="1">

```cpp
open_opts("f", {.create = true,
                .buffer = 4096});
// arm64 -O2:
//   mov  x1, #1
//   movk x1, #4096, lsl #32
//   b    open_opts
```

```cpp
open_pos("f", true, false,
         false, 4096);
// arm64 -O2:
//   mov w1, #1
//   mov w2, #0
//   mov w3, #0
//   mov w4, #4096
//   b   open_pos
```

</div>

Both put constants in registers and tail-call, with no extra memory access. When the struct exceeds 16 bytes, both platforms pass it through memory instead (arm64 passes a pointer to a copy, x86-64 SysV puts it on the stack), costing one extra memory write and read. Compared with the work the function itself does, this is usually negligible.

Another cost is in evolution. Adding members at the end or in the middle of an option aggregate doesn't affect callers using designated initializers; reordering existing members breaks every call that designates two or more of the reordered members. That is a breakage caught at compile time, which beats positional arguments silently shifting, but it also means member order becomes part of the interface.

## Builders and method chaining

An option aggregate is just a bundle of data. It cannot check constraints between fields (`append` and `truncate` cannot both be true), nor compute anything while being filled in. A **builder** is a class dedicated to collecting parameters: each parameter has a member function, and `build()` finally checks the constraints and constructs the result. If the member functions return a reference to the builder itself, calls can be strung together; this is called **method chaining**. In the standard library, `std::ostream`'s `operator<<` returns `ostream&`, the same technique.

### Returning `*this` by reference, and dangling

```cpp title="dangling-builder.cpp" run ub
#include <cstdio>
#include <string>

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder& url(std::string u) { url_ = std::move(u); return *this; }
  RequestBuilder& timeout(int s) { timeout_ = s; return *this; }
  void send() const { std::printf("GET %s (%ds)\n", url_.c_str(), timeout_); }
};

int main() {
  RequestBuilder{}.url("https://example.org/long/path").timeout(5).send();  // OK
  auto& b = RequestBuilder{}.url("https://example.org/long/path");
  b.timeout(5);   // UB: the temporary was destroyed at the end of the previous line
  b.send();
}
```

The first line is typical builder usage and entirely correct. `RequestBuilder{}` is a prvalue; calling a member function on it materializes a temporary ([[class.temporary#2]]), which is destroyed only as the last step of evaluating the whole **full-expression** ([[g:full-expression]], here the statement up to the semicolon) ([[class.temporary#4]]). Every call in the chain completes before that.

The second line binds the result of the chain to a reference. `url` has no ref-qualifier, and by [[over.match.funcs.general#5]], although the implicit object parameter of such a member function is a non-const lvalue reference, it may still bind to an rvalue, so calling it on a temporary is legal. The `RequestBuilder&` it returns refers to that temporary, but the reference `b` binds to the result of a function call, which is not one of the expressions listed in [[class.temporary#6]], so the temporary's lifetime is not extended; it is destroyed at the end of this line. `const auto&` behaves the same.

Clang 23 gives no warning at all. Run with `-fsanitize=address`, the third line reports `stack-use-after-scope`, with the write inside `RequestBuilder::timeout(int)` and the address in the temporary created on the second line. Add `[[clang::lifetimebound]]` after the declarator of `url` (applying to `*this`), and Clang gives `-Wdangling` for the second line. More dangling cases and tools are in [[topics/dangling-references]].

### Telling lvalues from temporaries with ref-qualifiers

Member functions can be overloaded on whether the object they are called on is an lvalue or an rvalue, by writing a **ref-qualifier** `&` or `&&` after the parameter list. By [[over.match.funcs.general#4]], the implicit object parameter of the `&` version is an lvalue reference and that of the `&&` version an rvalue reference; when both are viable, [[over.ics.rank#3.2.3]] makes rvalues prefer the `&&` version.

```cpp title="ref-qualified.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

struct Request { std::string url; int timeout; };

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder() = default;
  RequestBuilder(RequestBuilder&& o) noexcept
      : url_(std::move(o.url_)), timeout_(o.timeout_) { std::puts("  move"); }

  RequestBuilder& url(std::string u) & { url_ = std::move(u); return *this; }
  RequestBuilder  url(std::string u) && { url_ = std::move(u); return std::move(*this); }
  RequestBuilder& timeout(int s) & { timeout_ = s; return *this; }
  RequestBuilder  timeout(int s) && { timeout_ = s; return std::move(*this); }

  Request build() && { return {std::move(url_), timeout_}; }
};

int main() {
  std::puts("temporary chain:");
  Request r = RequestBuilder{}.url("https://example.org").timeout(5).build();
  std::puts("named builder:");
  RequestBuilder b;
  b.url("https://example.org").timeout(5);
  Request r2 = std::move(b).build();
  std::puts("bound to auto&&:");
  auto&& c = RequestBuilder{}.url("https://example.org");
  c.timeout(1);   // OK: c binds to a temporary whose lifetime was extended
  std::printf("%s %d / %s %d\n", r.url.c_str(), r.timeout, r2.url.c_str(), r2.timeout);
}
```

A named builder takes the `&` version, which returns a reference, with no moves. A temporary builder takes the `&&` version, which returns by value, each link moving the contents into a new prvalue: the output shows one move for each of the two calls in the temporary chain, and none for the named builder. `auto&& c` binds to the prvalue returned by value, and by [[class.temporary#6]] bullet 1 the materialized temporary lives as long as `c`, so the dangling is gone.

`build() &&` accepts only rvalues, so a named builder has to be written `std::move(b).build()`. That way `build` can move the members out, and the `std::move` at the call site reminds the reader that `b` should not be used afterwards.

The `&&` version could also return `RequestBuilder&&`, saving the move at each link. The price is that `auto&& c = RequestBuilder{}.url(...)` dangles again: ASan reports `stack-use-after-scope` in our tests too. Returning a value or an rvalue reference is a trade-off between safety and the number of moves.

After optimization the number of moves is usually not an issue. With Clang 23 at `-O2`, calling three setters on a temporary builder and then `build()` generates identical instructions whether the setters return `RequestBuilder` or `RequestBuilder&&`, 10 in both cases, only one register move more than the 9 for writing `Request{std::move(u), 5, 1}` directly. Once every call is inlined, the intermediate `std::string` moves are all eliminated.

!!! pitfall "You can't qualify half and leave half unqualified"
    Member functions with the same name and parameter list must either all have ref-qualifiers or all lack them. `B x(int);` together with `B x(int) &&;` is a conflicting redeclaration (example 2 in [[basic.scope.scope#4]]), and Clang reports an error. So when adding an `&&` overload for a setter, the original must be changed to `&`.

### deducing this: one template instead of two overloads {{c++23}}

Each setter is written twice with almost identical bodies. C++23's **explicit object parameter** ([[g:explicit-object-parameter]], [[P0847R7]]) writes the object as the first parameter, prefixed with `this` ([[dcl.fct#8]]). Written as `Self&&`, the parameter is a forwarding reference, and `Self` is deduced from the object: `RequestBuilder&` when called on an lvalue, `RequestBuilder` when called on an rvalue ([[temp.deduct.call#3]]).

```cpp title="deducing-this.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder() = default;
  RequestBuilder(RequestBuilder&& o) noexcept
      : url_(std::move(o.url_)), timeout_(o.timeout_) { std::puts("  move"); }

  template<class Self>
  Self url(this Self&& self, std::string u) {
    self.url_ = std::move(u);
    return std::forward<Self>(self);
  }
  template<class Self>
  Self timeout(this Self&& self, int s) {
    self.timeout_ = s;
    return std::forward<Self>(self);
  }
  void show() const { std::printf("%s %d\n", url_.c_str(), timeout_); }
};

class HttpRequestBuilder : public RequestBuilder {
  std::string header_;
public:
  template<class Self>
  Self header(this Self&& self, std::string h) {
    self.header_ = std::move(h);
    return std::forward<Self>(self);
  }
};

int main() {
  RequestBuilder b;
  b.url("https://example.org").timeout(5);        // Self = RequestBuilder&
  b.show();
  std::puts("temporary:");
  auto&& t = RequestBuilder{}.url("x").timeout(1);   // Self = RequestBuilder
  t.show();
  std::puts("derived:");
  HttpRequestBuilder{}.url("y").header("Accept: */*").timeout(2).show();
}
```

The return type is simply `Self`. Called on an lvalue it is `RequestBuilder&`, like the `&` version; called on an rvalue it is `RequestBuilder`, returned by value, like the `&&` version in the previous section. One template gets both behaviors: in the output the named builder never moves, and the temporary chain moves once per link.

The last line is an extra benefit of this approach. `url` is defined in the base, but called on an `HttpRequestBuilder`, `Self` is deduced as `HttpRequestBuilder`, so it still returns the derived type and `header` can follow. With the previous section's approach, `url` returns `RequestBuilder`, and chaining `header` reports no member named 'header'. Before C++23, achieving this meant making the base a template and passing the derived class in as a template argument; see [[patterns/crtp]].

<details class="fine" markdown="1"><summary>Some details of explicit object parameters</summary>

- There is no implicit `this` in the body; members must be accessed as `self.url_`. Names are looked up in the type of `Self`, so if a derived class declares a member with the same name, that is the one found.
- `self.url_` is a private member of the base accessed through a derived object. Under public inheritance this is allowed, because the access happens in a member function of the base, where `url_` as a member of the base is accessible ([[class.access.base#5]]). Under private inheritance this path is blocked and compilation fails.
- Called on a `const` object, `Self` is deduced as `const RequestBuilder&`, and the assignment `self.url_ = ...` fails at instantiation. That is the desired outcome, except the diagnostic appears in the function body rather than at overload resolution.
- The setters are now templates, so their definitions must be visible to callers, usually in a header.

</details>

### A validating builder

What a builder can do beyond an option aggregate is check the parameters before constructing the result. Checks can fail, so `build()` can return `std::expected` ([[expected]], {{c++23}}): either the constructed object or an error.

```cpp title="validating-builder.cpp" run ok
#include <cstdio>
#include <expected>
#include <string>
#include <utility>

class Request {
  std::string url_;
  int timeout_;
  Request(std::string u, int t) : url_(std::move(u)), timeout_(t) {}
  friend class RequestBuilder;
public:
  const std::string& url() const { return url_; }
  int timeout() const { return timeout_; }
};

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder& url(std::string u) { url_ = std::move(u); return *this; }
  RequestBuilder& timeout(int s) { timeout_ = s; return *this; }

  std::expected<Request, std::string> build() const {
    if (url_.empty())
      return std::unexpected("url is required");
    if (timeout_ <= 0)
      return std::unexpected("timeout must be positive");
    return Request(url_, timeout_);
  }
};

int main() {
  auto r = RequestBuilder{}.url("https://example.org").timeout(5).build();
  if (r) std::printf("%s %d\n", r->url().c_str(), r->timeout());
  auto e = RequestBuilder{}.timeout(0).build();
  if (!e) std::printf("error: %s\n", e.error().c_str());
}
```

`Request`'s constructor is private and only the builder can create one, so every `Request` object has been validated. The setters here have no ref-qualifiers, but every chain ends within one full-expression and `build()` returns a value, so nothing dangles. The second line of output is `error: url is required`; the first check fails first.

Whether a failed validation should throw or return `expected` depends on whether callers often need to handle the failure; see the discussion at the end of [[topics/exception-safety]].

### Choosing between a builder and an option aggregate

<div class="compare" markdown="1">

```cpp
// option aggregate
connect({.host = "example.org",
         .port = 8443});
```

```cpp
// builder
auto c = ConnBuilder{}
    .host("example.org")
    .port(8443)
    .build();
```

</div>

An option aggregate is short to write and has zero run-time overhead, but it can only express a set of independent fields each with a default, and validation has to wait until the function that uses it. A builder needs one member function per field, and in exchange gets constraint checks between fields, step-by-step filling (setters can be called in loops or conditionals), and a single exit point at `build()`.

## Traps of default arguments

The simplest optional parameter is a default argument: `void open_file(std::string_view path, int buffer = 8192);`. It doesn't solve naming, can only omit trailing arguments, and has a few rules that are easy to get wrong. The detailed analysis is in [[dcl.fct.default]]; here are the ones that matter for interface design.

**Default arguments are expanded at the caller.** When `f()` is called, the compiler fills in the default argument expression at the call site, evaluated once per call ([[dcl.fct.default#9]], [[expr.call#7]]). The consequence is that the default value is compiled into the caller:

```cpp title="lib.h"
void set_level(int level = 1);
```

In our tests, compiling `main.cpp` (which calls `set_level()`) and `lib.cpp` separately with this header and running prints `level 1`. Change the header to `= 2`, recompile only `lib.cpp` and relink, and it still prints `level 1`. For a shared library, the default value is effectively part of the caller, and changing it requires recompiling every caller.

**Default arguments of virtual functions follow the static type.** [[dcl.fct.default#10]] says a virtual function call uses the default arguments determined by the static type of the pointer or reference denoting the object, while the function called is chosen by dynamic type:

```cpp title="virtual-default.cpp" run ok
#include <cstdio>

struct Logger {
  virtual void log(const char* msg, int level = 1) { std::printf("base %s %d\n", msg, level); }
  virtual ~Logger() = default;
};
struct FileLogger : Logger {
  void log(const char* msg, int level = 3) override { std::printf("file %s %d\n", msg, level); }
};

int main() {
  FileLogger f;
  Logger& r = f;
  r.log("a");   // file a 1: function chosen by dynamic type, default argument by static type
  f.log("b");   // file b 3
}
```

`r.log("a")` runs `FileLogger::log` but gets the `1` from `Logger`'s declaration. The behavior is well defined; it is just rarely what anyone wants. The usual approach is to put default arguments only on a non-virtual public function that forwards to the virtual one; see [[patterns/nvi]].

**Default arguments are not part of the function type** ([[dcl.fct.default#9]]). The type of `&open_file` carries no default values, so calls through a function pointer or `std::function` must supply every argument.

**Redeclarations can add defaults but not repeat them.** A later declaration in the same scope may add default arguments for more parameters, but may not give the same parameter a default again, even with the same value; declarations in block scope each have their own set ([[dcl.fct.default#4]]). Putting defaults in the header declaration and not in the `.cpp` definition is the least error-prone habit.

**Combined with overloading, they easily cause ambiguity.** `void f(int, int = 0);` and `void f(int);` can be declared together, but `f(1)` is ambiguous; Clang reports call to 'f' is ambiguous.

## How to choose

| Situation | Approach |
|---|---|
| One or two switch parameters | scoped enumerations, `enum class X : bool` |
| Same-typed numeric parameters that are easy to swap | [[patterns/strong-types\|strong types]] |
| A group of independent options, all with defaults | option aggregate + designated initializers |
| Constraints between options, or step-by-step filling | builder, validating in `build()`, returning `expected` or throwing on failure |
| Builders chained on temporaries whose result may be bound to a reference | `&` / `&&` overloads with `&&` returning by value; in C++23 deducing this |
| A derived builder that should reuse the base's setters | deducing this, returning `Self` |
| Just omitting one or two trailing parameters, not a virtual function, not a stable library interface | default arguments |

## Questions

!!! question "1"
    `open_file("f", {.buffer = 4096, .create = true})` produces only one warning with Clang 23 and `-Wall -Wextra`, and the program runs. Is it well-formed? If `open_file` had another overload taking `struct Other { int buffer; bool create; }`, what would happen?

<details markdown="1">
<summary>Answer</summary>

It is ill-formed. [[dcl.init.list#3]] bullet 1 requires designated members to be in non-decreasing element order; `buffer` is declared after `create`, which violates this diagnosable rule. Clang accepts it as a C99 extension with `-Wreorder-init-list`, and reports an error only with `-pedantic-errors`.

With the `Other` overload added, by [[over.ics.list#2]], both parameter types have members `buffer` and `create` and can be aggregate-initialized from the list; order is not considered during overload resolution, so the call is ambiguous. That the order happens to match `Other`'s declaration does not help it win.
</details>

!!! question "2"
    Change the second line of `dangling-builder.cpp` to `const auto& b = RequestBuilder{}.url("...");`, delete the call to `b.timeout`, and keep only `b.send()`. A const reference extends the lifetime of a temporary; does it still dangle?

<details markdown="1">
<summary>Answer</summary>

It still dangles. Lifetime extension happens only when the glvalue the reference binds to was obtained through one of the expressions listed in [[class.temporary#6]]: temporary materialization, parentheses, data member access, certain casts, and so on. `url(...)` is a function call, and where the returned reference points cannot be seen at the call site, so it is not on the list. Whether the reference is `const` makes no difference. ASan in our tests reports `stack-use-after-scope` for `b.send()` too. For the binding to be safe, the `&&` version must return by value.
</details>

!!! question "3"
    Someone adds `OpenOptions() = default;` to `OpenOptions` to make the intent of default construction clearer. What happens to all the calls using designated initializers?

<details markdown="1">
<summary>Answer</summary>

They all fail to compile. From C++20 an aggregate may not have any user-declared constructor, including defaulted ones ([[dcl.init.aggr#1]] bullet 1, [[P1008R1]]). `OpenOptions` is no longer an aggregate, and by [[over.ics.list#2]] there is no implicit conversion from a designated list to it; Clang reports no matching function for call to 'open_file'. Writing `OpenOptions o{.create = true};` directly also fails [[dcl.init.list#3]] bullet 1, and Clang reports initialization of non-aggregate type 'OpenOptions' with a designated initializer list. Remove the line; the default member initializers already express the defaults.
</details>
