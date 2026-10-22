---
title: Name lookup, ADL and customization points
summary: "How the compiler finds the declaration for a name: qualified and unqualified lookup, hiding, argument-dependent lookup and when it is turned off, hidden friends and operator lookup, and the successive generations of design the standard library has used to let users customize behavior."
tags: name lookup, ADL, hidden friends, customization points, CPO, topic
updated: 2026-10-19
---

!!! tldr
    - The qualified name `std::swap` is looked up only in `std`. The unqualified name `swap` is searched for scope by scope outward from the point of the call, stopping at the first scope that has the name; all declarations of the same name in outer scopes are hidden.
    - Unqualified function calls also get ADL: functions are looked up in the namespaces of the argument types (including template arguments). That is how `using std::swap; swap(a, b);` finds the user's `swap`.
    - If the name is parenthesized, or ordinary lookup finds a class member, a block-scope function declaration, a variable or a function object, ADL is not performed.
    - A friend function declared only inside a class (a hidden friend) can only be found through ADL. Writing operators as hidden friends keeps overload sets minimal and avoids them being picked through implicit conversions.
    - Standard library customization points have gone through four generations: free functions found by ADL, specializing class templates in `std`, customization point objects (`std::ranges::swap`), and `tag_invoke`; C++26's `std::execution` switched to calling member functions. Adding overloads to `std` is UB.

## The same swap, called two ways

```cpp run title="swap.cpp" ok
#include <cstdio>
#include <utility>
#include <concepts>
namespace app {
struct Buf {
  int* data;
  friend void swap(Buf& a, Buf& b) noexcept {
    std::puts("app::swap");
    std::swap(a.data, b.data);
  }
};
}
int main() {
  app::Buf a{}, b{};
  std::swap(a, b);           // qualified name: looked up only in std
  using std::swap;
  swap(a, b);                // unqualified name: ADL finds app::swap
  std::ranges::swap(a, b);   // customization point object: does ADL for you
}
```

The program prints `app::swap` only twice. The first call, `std::swap(a, b)`, uses the standard library's generic version, which swaps with one move construction and two move assignments; the user's `swap` is not even a candidate.

The difference lies entirely in [[g:name-lookup|name lookup]]: the compiler finding the declaration for a name that appears in the code. Lookup happens before overload resolution, and only functions that lookup finds are eligible for overload resolution ([[basic.lookup.general#1]]). So the question to answer here is which functions lookup found, not which function is a better match.

## Two kinds of lookup: qualified and unqualified

`std::swap` is a [[g:qualified-name|qualified name]]: the name is preceded by `X::`, or appears after `obj.` or `p->`. A qualified name is looked up only in the class or namespace specified ([[basic.lookup.qual]]). When looking in a namespace, its inline namespaces are searched too; if nothing is found, lookup continues through the using-directives in that namespace ([[namespace.qual#1]]). So `std::swap` only ever finds the `swap` in `std`.

`swap` is an [[g:unqualified-name|unqualified name]]. Starting from where the name appears, it is searched for in the current scope; only if nothing is found does the search continue in the next enclosing scope, all the way to the global namespace ([[basic.lookup.unqual#2]]). So as soon as any declaration of the name is found at some level, lookup stops at that level.

<div class="compare" markdown="1">

```cpp error
void log(int);
namespace app {
void log(const char*);
void run() {
  log(42);   // error: ::log is hidden
}
}
```

```cpp ok
void log(int);
namespace app {
void log(const char*);
using ::log;   // brings ::log into app
void run() {
  log(42);     // OK: calls ::log(int)
}
}
```

</div>

On the left, lookup finds `log(const char*)` in `app` and doesn't go on to the global namespace, so `::log(int)` never becomes a candidate. Clang 23 lists only one candidate:

```text
error: no matching function for call to 'log'
note: candidate function not viable: no known conversion from 'int' to 'const char *' for 1st argument
```

This is called **hiding**. Hiding looks only at the name, not at whether parameter types match, let alone which is better. On the right, the using-declaration puts `::log` into `app` as well, so both functions are found at the same level and handed to overload resolution.

Class scope works the same way: if a derived class declares `f`, all `f`s in the base class are hidden, and a call `f(42)` in a member function sees only the derived class's version ([[class.member.lookup]]). The fix is likewise to write `using Base::f;` in the derived class.

## ADL: looking in the namespaces of the argument types

If unqualified lookup were the whole story, `using std::swap; swap(a, b);` would only find `std::swap`. It finds `app::swap` because an unqualified name in a function call also undergoes [[g:argument-dependent-lookup|argument-dependent lookup]] (ADL): a set of [[g:associated-namespaces|associated namespaces]] is determined from the types of the arguments, functions with the same name are looked up in those namespaces, and the results are merged with those of ordinary lookup into one overload set ([[basic.lookup.argdep#1]]).

The type of `a` is `app::Buf`, whose associated namespace is `app`, so `app::swap` joins the candidates. The overload set is `{std::swap<Buf>, app::swap}`, and the latter, not being a template, wins ([[over.match.best]]). For `int`, fundamental types have no associated namespaces, ADL adds nothing, and `std::swap` is used. The `using std::swap;` line is the fallback for exactly this case.

Associated namespaces are determined by the [[g:associated-entities|associated entities]] of the argument types; the rules are in [[basic.lookup.argdep#3]], and [[basic.lookup.argdep]] has examples for each. The main points:

| Argument type | Associated entities it brings |
|---|---|
| Fundamental types such as `int`, `double`, `nullptr_t` | None |
| Class `C` | `C` itself; if `C` is nested, its enclosing class; if `C` is complete, all its base classes |
| Class template specialization `X<A, B>` | Everything in the previous row, plus the associated entities of the type template arguments `A` and `B` |
| Enumeration | The enumeration itself; if it is a class member, that class |
| Pointer, array | The associated entities of the element type |
| Function type, function pointer | The associated entities of the parameter and return types |

The associated namespaces are the innermost enclosing namespaces of these entities, plus any inline namespaces in them ([[basic.lookup.argdep#4]]). Typedefs and aliases play no part; only the type they denote matters.

The template argument row is the one most likely to surprise. The associated namespaces of `std::vector<app::Point>` are `std` and `app`, so an unqualified call in generic code can be taken over by a function that happens to have the same name in either namespace:

```cpp run title="hijack.cpp" ok
#include <cstdio>
#include <vector>
namespace lib {
template<class C> int size(const C& c) { return int(c.size()); }
template<class C> void report(const C& c) {
  std::printf("%d\n", size(c));   // the author's intent: call lib::size
}
}
namespace app {
struct Point { int x, y; };
int size(const std::vector<Point>&) { return -1; }
}
int main() {
  std::vector<app::Point> v(3);
  lib::report(v);   // prints -1
}
```

`size(c)` in `report` depends on a template parameter, so ADL happens at instantiation (see [[topics/two-phase-lookup]]). There are three candidates: `lib::size` found by ordinary lookup, `std::size` found by ADL in `std` (since C++17), and `app::size` found by ADL in `app`. The last one isn't a template and wins.

Deleting `app::size` doesn't restore the author's intent either: `lib::size` and `std::size` both take `const C&` and are equally good, and Clang 23 reports `call to 'size' is ambiguous`. It's the same mechanism: when a type's author provides it on purpose it's called customization; when the name happens to collide, it's called hijacking.

## When there is no ADL

[[basic.lookup.argdep#1]] says ADL is performed only if the called part is an unparenthesized unqualified name, and ordinary unqualified lookup did not find any of these three kinds of declaration:

- A declaration of a class member (¶1.1);
- A function declaration at block scope (¶1.2);
- A declaration that is not a function or function template, such as a variable, a function object or a type (¶1.3).

```cpp title="no-adl.cpp" error
namespace N {
struct S {};
void f(S);
}
void a() { N::S s; f(s); }     // OK: ADL finds N::f
void b() { N::S s; (f)(s); }   // error: parentheses turn off ADL
void c() {
  N::S s;
  void f(int);                 // block-scope function declaration
  f(s);                        // error: ADL turned off, only f(int) remains
}
```

Clang 23 reports `use of undeclared identifier 'f'; did you mean 'N::f'?` for `b`, and `no viable conversion from 'N::S' to 'int'` for `c`.

A `using std::swap;` at block scope doesn't turn off ADL. When a using-declaration is found, it is replaced by the declarations it names ([[basic.lookup.general#3]]), here the function templates in `std`. Those don't inhabit the block scope, so ¶1.2 doesn't apply.

¶1.3 is the basis for the customization point objects described later: when ordinary lookup finds a variable, ADL is not performed.

```cpp run title="object.cpp" ok
#include <cstdio>
namespace N {
struct S {};
void f(S) { std::puts("N::f"); }
}
inline constexpr auto f = [](auto) { std::puts("::f object"); };
int main() {
  N::S s;
  f(s);   // finds the variable ::f, ADL is turned off, prints "::f object"
}
```

¶1.1 most often causes trouble in member functions. If a class has its own member named `swap`, an unqualified `swap(x, y)` in one of its member functions finds the member in class scope, and ADL is turned off:

<div class="compare" markdown="1">

```cpp error
#include <string>
#include <utility>
struct Person {
  std::string name;
  void swap(Person& o) noexcept {
    swap(name, o.name);
    // error: finds member swap
  }
};
```

```cpp ok
#include <string>
#include <utility>
struct Person {
  std::string name;
  void swap(Person& o) noexcept {
    using std::swap;
    swap(name, o.name);   // OK
  }
};
```

</div>

The error on the left is `too many arguments to function call, expected 1, have 2`: the compiler only sees the member `Person::swap(Person&)`. On the right, the block scope is searched before the class scope, lookup stops at the using-declaration, which names functions in a namespace, and ADL goes ahead as usual.

## Hidden friends

```cpp title="hidden-friend.cpp" error
namespace geo {
struct Point {
  int x, y;
  friend bool operator==(const Point&, const Point&) = default;
};
}
bool a(geo::Point p, geo::Point q) { return p == q; }            // OK: ADL
bool b(geo::Point p, geo::Point q) { return operator==(p, q); }  // OK: also ADL
bool c(geo::Point p, geo::Point q) {
  return geo::operator==(p, q);   // error: qualified lookup can't find it
}
```

The friend declaration `friend bool operator==(...)` in the class declares a function in the enclosing namespace `geo`, but a friend declaration doesn't introduce the name into any scope (¶2.1 of [[dcl.meaning.general#2]], [[class.friend#10]]). Unless it is declared again at namespace scope, neither ordinary lookup nor qualified lookup can find it; Clang 23 reports `no member named 'operator==' in namespace 'geo'` for `c`.

ADL is the only exception: it also finds friend functions declared in associated classes (¶4.2 of [[basic.lookup.argdep#4]]). Such a friend function declared only within a class is called a [[g:hidden-friend|hidden friend]]. Writing operators and customization functions like `swap` as hidden friends has three advantages.

First, smaller overload sets. A namespace-scope operator takes part in every lookup of that operator in the namespace. The two programs below both define 100 types and their `operator<<` in namespace `big`, then write `os << x` for a `big::Unprintable` that has no `operator<<`:

| Form | Candidates listed by Clang 23 |
|---|---|
| 100 namespace-scope `operator<<` | 151 (100 from `big`, 51 from libc++) |
| 100 hidden friend `operator<<` | 51 (all from libc++) |

A hidden friend enters the candidate set only when the argument's associated class is exactly the class it's in. With the namespace-scope versions, template argument deduction and implicit conversion checks have to be done for all of them every time, so compilation is slower and error messages are longer.

Second, they aren't picked by mistake through implicit conversions. A type that merely converts to `Point` doesn't have `Point` among its associated entities, so it can't find `Point`'s hidden friends. [[basic.lookup.argdep]] has a runnable comparison.

Third, they can access private members, so you don't need to expose getters just to write operators.

## How operators are looked up

An operator expression `a << b` is first rewritten into function call form, and then three kinds of candidates are collected according to [[over.match.oper#3]]:

- Member candidates: `operator<<` is looked up in the class of `a` (¶3.1);
- Non-member candidates: unqualified lookup plus ADL for `operator<<`, ignoring all member functions found (¶3.2);
- Built-in candidates: such as the built-in shift for `int << int` (¶3.3).

There's no parenthesized or qualified form of an operator, so ADL is always performed. That ¶3.2 ignores member functions also leads to a result different from a named call:

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <string>
struct Logger {
  Logger& operator<<(int) {
    return *this;
  }
  void dump(const std::string& s) {
    std::cout << s << '\n';   // OK
  }
};
int main() { Logger{}.dump("hi"); }
```

```cpp error
#include <iostream>
#include <string>
struct Logger {
  Logger& operator<<(int) {
    return *this;
  }
  void dump(const std::string& s) {
    operator<<(std::cout, s);
    // error: finds the member, ADL turned off
  }
};
```

</div>

On the left, `std::cout << s` is written in a member function of `Logger`. Unqualified lookup first finds `Logger::operator<<` in class scope, but non-member lookup for operators ignores members, ADL proceeds as usual, and finds the `operator<<` in `std` that accepts `std::string`. On the right, the same thing written as a named function call falls under ¶1.1 of [[basic.lookup.argdep#1]], ADL is turned off, and Clang 23 reports `too many arguments to function call, expected 1, have 2`.

Non-member operator lookup can still be hidden: once any `operator<<` is declared in a namespace, `operator<<`s in enclosing namespaces can only be found through ADL. An `operator<<` for `std::vector<int>` written in the global namespace can never be found by ADL, because the only associated namespace of `std::vector<int>` is `std`. Puzzle 2 in [[topics/two-phase-lookup]] shows the consequences. Operators for a type should be placed in that type's namespace, preferably as hidden friends.

## Generations of customization point design

Generic libraries often need to call an operation whose behavior is determined by the user's type: swapping two objects, getting the start of a range, computing a hash. The place in the library that calls such an operation is called a **customization point**. C++ has used several designs over time, each patching the problems of the one before.

### First generation: overloadable free functions

`swap`, `begin`/`end` and `operator<<` belong to this generation. The library writes an unqualified call in generic code, the user provides a function with the same name in their own namespace, and ADL connects the two. Its problems have all appeared above:

- Callers have to remember to write `using std::swap; swap(a, b);`; writing `std::swap(a, b)` quietly bypasses the user's customization;
- Unqualified calls can be hijacked by functions that happen to share the name, or become ambiguous (`hijack.cpp`);
- The library can't check whether the user's function really meets the requirements, for example whether `swap` really swaps two values.

### Second generation: specializing class templates in std

`std::hash`, `std::tuple_size` and `std::formatter` belong to this generation: the user specializes a standard library class template for their own type.

```cpp run title="hash.cpp" ok
#include <cstddef>
#include <functional>
#include <string>
#include <unordered_set>
namespace app {
struct Id {
  std::string name;
  int n;
  bool operator==(const Id&) const = default;
};
}
template<>
struct std::hash<app::Id> {
  std::size_t operator()(const app::Id& id) const noexcept {
    return std::hash<std::string>{}(id.name) ^ std::size_t(id.n);
  }
};
int main() {
  std::unordered_set<app::Id> s{{"a", 1}, {"a", 1}};
  return int(s.size()) - 1;   // returns 0
}
```

The specialization doesn't have to be written inside `namespace std { }`; it can be declared at global scope with a qualified name like `std::hash<app::Id>` ([[temp.expl.spec#3]]). This design doesn't rely on ADL, since a specialization of a class template can always be found; the cost is that the user has to leave their own namespace to write a chunk of boilerplate, and it only works for class templates.

The tuple protocol for structured bindings mixes the two generations. For a type to support `auto [k, v] = e;`, you specialize `std::tuple_size` and `std::tuple_element` and then provide `get<i>`. By [[dcl.struct.bind#7]], if the class has a suitable member template `get`, `e.get<i>()` is called; otherwise `get<i>(e)` is called, with ADL only and no ordinary unqualified lookup:

```cpp run title="tuple-protocol.cpp" ok
#include <cstddef>
#include <cstdio>
#include <string>
#include <tuple>
namespace app {
class Entry {
  std::string key_ = "k";
  int value_ = 42;
  template<std::size_t I>
  friend auto get(const Entry& e) {      // hidden friend: found through ADL
    if constexpr (I == 0) return e.key_;
    else return e.value_;
  }
};
}
template<>
struct std::tuple_size<app::Entry> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I>
struct std::tuple_element<I, app::Entry> {
  using type = std::conditional_t<I == 0, std::string, int>;
};
int main() {
  auto [k, v] = app::Entry{};
  std::printf("%s %d\n", k.c_str(), v);   // prints k 42
}
```

### Third generation: customization point objects {{c++20}}

[[N4381]] proposed making a customization point a global function object, and C++20's ranges library was designed that way. The standard calls such an object a [[g:customization-point-object|customization point object]] (CPO, [[customization.point.object#1]]). `std::ranges::swap` and `std::ranges::begin` are CPOs.

It solves all three problems of the first generation at once:

- Callers just write `std::ranges::swap(a, b)`. It's a qualified name that finds an object, so it can't be hijacked and doesn't need the two-step.
- ADL only collects functions and can never find this object ([[basic.lookup.argdep#4]]); if someone writes `using namespace std::ranges;` and then calls `swap(a, b)` unqualified, ordinary lookup finds the variable, and ADL is turned off by ¶1.3.
- The object's `operator()` looks up the user's customization in a controlled way and checks the semantic requirements. If no suitable customization is found, it falls back to a generic implementation; `operator()` itself is constrained and doesn't take part in overload resolution when the requirements aren't met ([[customization.point.object#4]]).

Taking `ranges::swap(E1, E2)` as an example, [[concept.swappable#2]] tries three approaches in order:

1. If one of the arguments has class or enumeration type and the unqualified call `swap(E1, E2)` is valid, call it. The context of this overload resolution doesn't contain `ranges::swap` itself, but a deleted declaration `template<class T> void swap(T&, T&) = delete;` (¶2.1);
2. If the two arguments are arrays of the same length, swap element by element (¶2.2);
3. If the two arguments are lvalues of the same type and are move constructible and move assignable, swap by moving (¶2.3).

The deleted declaration in step 1 is commonly called a **poison pill**. It makes lookup stop there, so it doesn't go out and find unconstrained templates like `std::swap`. It also takes part in overload resolution, which has a surprising consequence: an unconstrained `swap` template written by the user in their own namespace is just as good as the poison pill, the result is ambiguous, step 1 is invalid, and the user's `swap` is quietly skipped.

```cpp run title="poison-pill.cpp" ok
#include <concepts>
#include <cstdio>
#include <utility>
namespace app {
struct A { int v; };
template<class T> void swap(T& x, T& y) {   // unconstrained template
  std::puts("app::swap<T>");
  std::swap(x.v, y.v);
}
struct B { int v; };
void swap(B& x, B& y) {                     // non-template
  std::puts("app::swap(B&, B&)");
  std::swap(x.v, y.v);
}
}
int main() {
  app::A a1{1}, a2{2};
  app::B b1{1}, b2{2};
  std::ranges::swap(a1, a2);   // prints nothing: falls back to step 3, swaps by moving
  std::ranges::swap(b1, b2);   // prints app::swap(B&, B&)
  std::printf("%d %d\n", a1.v, b1.v);   // 2 2
}
```

The note in ¶2.1 says explicitly that this excludes unconstrained user `swap`s, and that a user's overload is selected only if it is more specialized than the poison pill. A non-template `swap` for a specific type, or one written as a hidden friend, satisfies this.

`ranges::begin` also used to have a poison pill; C++23's [[P2602R2]] removed it as a defect report. The current rule is: if the member `t.begin()` is usable, use it; otherwise, for class or enumeration types, call `begin(t)` as if with ADL only (¶2.5 of [[range.access.begin#2]]). Like the member version, a non-member `begin` found by ADL must return a type satisfying `input_or_output_iterator`, or that step doesn't apply. Details are in [[range.access]].

The algorithms in `std::ranges` (`find`, `sort`, …) are objects too; the standard calls them **algorithm function objects** ([[alg.func.obj#2]]), commonly known as niebloids. They don't customize anything; they are objects only so that ADL can't find them and so that ADL is turned off when ordinary lookup finds them, ensuring that `find(...)` after `using namespace std::ranges;` calls the constrained ranges version.

### Fourth generation: tag_invoke

CPOs solved the caller's problem, but every CPO requires the library author to hand-write a set of lookup rules, and users have to know which name each CPO recognizes. [[P1895R0]] proposed `tag_invoke`: all customization points share one function name, `tag_invoke`, and the type of the CPO itself, passed as the first argument, distinguishes the customization points.

```cpp run title="tag-invoke.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

namespace lib {
namespace detail {
void tag_invoke();   // makes the lookup below stop here and not search outward
struct tag_invoke_fn {
  template<class Tag, class... Args>
  constexpr auto operator()(Tag tag, Args&&... args) const
      -> decltype(tag_invoke(tag, std::forward<Args>(args)...)) {
    return tag_invoke(tag, std::forward<Args>(args)...);   // the only ADL call site
  }
};
}
inline constexpr detail::tag_invoke_fn tag_invoke{};

struct to_string_fn {   // one customization point = one type
  template<class T>
  std::string operator()(const T& x) const { return lib::tag_invoke(*this, x); }
};
inline constexpr to_string_fn to_string{};
}

namespace app {
struct Point {
  int x, y;
  friend std::string tag_invoke(lib::to_string_fn, const Point& p) {
    return std::to_string(p.x) + "," + std::to_string(p.y);
  }
};
}

int main() { std::puts(lib::to_string(app::Point{1, 2}).c_str()); }   // prints 1,2
```

What the user writes to customize is `tag_invoke(lib::to_string_fn, ...)`, which won't collide with functions named `to_string` from other libraries. The library author only needs to write one ADL call site.

Its drawbacks are obvious too. Every customization is named `tag_invoke`, so one type may have dozens of such overloads, and every call has to do overload resolution over all of them: compilation is slow and error messages are hard to read; the signature of a customization function doesn't show what it customizes, except through the type of its first parameter. Some proposals (such as [[P2547R1]]) have tried to support customizable functions directly with a language mechanism; as of the current draft none has entered the standard.

### C++26's std::execution: member functions {{c++26}}

`std::execution` (the sender/receiver model) used `tag_invoke` during its design; [[P2855R1]] changed it to call member functions directly, and that is the version C++26 adopted. For example:

- `execution::connect(sndr, rcvr)` is, when viable, equivalent to `new_sndr.connect(rcvr)`, where `new_sndr` is the sender after transforming `sndr` ([[exec.connect#6]]);
- `execution::set_value(rcvr, vs...)` is equivalent to `rcvr.set_value(vs...)`, and requires `rcvr` to be a non-const rvalue ([[exec.set.value#1]]);
- `execution::get_env(o)` calls `o.get_env()`, returning an empty environment if there is no such member ([[exec.get.env#1]]).

So a receiver is just an ordinary class:

```cpp
struct print_receiver {
  using receiver_concept = std::execution::receiver_tag;
  void set_value(int v) && noexcept { std::printf("%d\n", v); }
  void set_error(std::exception_ptr) && noexcept {}
  void set_stopped() && noexcept {}
};
```

Names like `connect` and `set_value` are still CPOs, and the way callers write them hasn't changed; what changed is how users supply customizations, from free functions found by ADL to member functions. The lookup rules are just ordinary member lookup, with no hijacking and no huge overload sets. Customizing algorithms per execution resource uses a **domain**: a class whose member `transform_sender` rewrites senders ([[exec.snd.transform#3]]). The `receiver_tag` in the example above is the name in the current draft ([[exec.recv.concepts#1]]). libc++ in our tests doesn't implement `std::execution` yet, so this code hasn't been verified.

### The generations compared

| Design | Examples | How users customize | How callers write it | Main problems |
|---|---|---|---|---|
| ADL free functions | `swap`, `begin`, `operator<<` | Write a function with the same name in their own namespace | `using std::swap; swap(a, b);` | Easy to get wrong; can be hijacked; semantics unchecked |
| Specializing class templates | `std::hash`, `tuple_size`, `formatter` | Specialize a class template in `std` | `std::hash<T>{}(x)` | Lots of boilerplate; class templates only |
| CPO | `ranges::swap`, `ranges::begin` | Free function with the same name (hidden friend) or member | `std::ranges::swap(a, b)` | Each CPO has different rules; poison pill surprises |
| `tag_invoke` | Early `std::execution` | `tag_invoke(cpo_type, ...)` | `cpo(args...)` | Huge overload sets; hard-to-read signatures |
| Member functions | C++26 `std::execution` | Write member functions | `cpo(args...)` | Can only customize your own types |

## What may be added to std

Since `std::swap` can't find the user's function, a common idea is to put the overload directly into `std`:

<div class="compare" markdown="1">

```cpp ub
#include <utility>
namespace app { struct X {}; }
namespace std {
void swap(app::X&, app::X&) noexcept;
// UB: adds a declaration to std
}
```

```cpp ok
#include <utility>
namespace app {
struct X {
  friend void swap(X&, X&) noexcept {}
};
}
```

</div>

[[namespace.std#1]] says that, unless otherwise specified, adding declarations or definitions to `std` or a namespace within it is undefined behavior. The main "otherwise specified" case is ¶2: specializations of standard library class templates may be added, provided the specialization depends on at least one program-defined type and meets the requirements of the original template. `std::hash<app::Id>` and `std::tuple_size<app::Entry>` belong to this category.

Since C++20, standard library function templates may no longer be specialized ([[P0551R3]]), so `template<> void std::swap<app::X>(...)` is UB too. The only correct way to customize `swap` is to write an overload in the type's own namespace, preferably as a hidden friend. The full list is in [[namespace.std]].

## Common misconceptions

!!! pitfall "Overload resolution picks the best of all functions with the same name"
    Overload resolution only chooses among the functions that lookup found. When outer functions are hidden or ADL is turned off, a better function isn't even a candidate, and the compiler won't tell you it exists.

!!! pitfall "Writing std::swap is the safest"
    In generic code, `std::swap(a, b)` never calls the `swap` users wrote for their own types; the result is three moves, correct but slower. Either use the two-step or use `std::ranges::swap`.

!!! pitfall "ADL only looks at the argument's own type"
    Template arguments, base classes, enclosing classes, and the parameter types of function pointers all bring in associated namespaces. When naming helper functions in a generic library with common names like `size`, `distance` or `find`, functions of the same name in user types' namespaces or in `std` can all be pulled in by ADL.

!!! pitfall "A hidden friend can be called as N::f"
    A friend declaration doesn't bind the name, so a hidden friend can only be found through ADL. If you need a function that can be called with qualification, declare it again at namespace scope, but then it is no longer a hidden friend.

## Questions

!!! question "1"
    ```cpp
    #include <vector>
    struct Range {
      std::vector<int> v;
      std::vector<int>::iterator begin() { return begin(v); }
    };
    ```
    Does this code compile?

<details markdown="1">
<summary>Answer</summary>

No. In the member function `begin`, unqualified lookup first finds the member `Range::begin()` in class scope, which turns off ADL by ¶1.1 of [[basic.lookup.argdep#1]], so `std::begin` never gets a chance to be a candidate. Clang 23 reports `too many arguments to function call, expected 0, have 1; did you mean 'std::begin'?`. Change it to `using std::begin; return begin(v);`, or simply write `v.begin()`.
</details>

!!! question "2"
    `app` contains only an unconstrained `template<class T> void swap(T&, T&)`. What happens with `using std::swap; swap(x, y);` for an `app::A`? What about `std::ranges::swap(x, y)`?

<details markdown="1">
<summary>Answer</summary>

The two-step is ambiguous. The overload set contains `std::swap<app::A>` and `app::swap<app::A>`; both templates take `T&` and are equally specialized under partial ordering, and Clang 23 reports `call to 'swap' is ambiguous`.

`std::ranges::swap` compiles but doesn't call `app::swap`. In step 1 the user's template is ambiguous with the poison pill, so the expression is invalid; step 3 swaps by moving ([[concept.swappable#2]]). Neither form calls this `swap`; it should be changed into a non-template function for `A`, or be constrained.
</details>

!!! question "3"
    Does `int arr[3]; auto b = begin(arr);` compile without `using std::begin;`? What about `std::vector<int> v; auto a = begin(v);`?

<details markdown="1">
<summary>Answer</summary>

`begin(v)` does: the associated namespace of `std::vector<int>` is `std`, and ADL finds `std::begin`. `begin(arr)` doesn't: the associated entities of an array are those of its element type, `int` brings nothing, and Clang 23 reports `use of undeclared identifier 'begin'; did you mean 'std::begin'?`. `std::ranges::begin(arr)` has a dedicated rule for arrays (¶2.3 of [[range.access.begin#2]]) and doesn't need ADL.
</details>

## Summary

| Question | Rule |
|---|---|
| Where is `X::f` looked up | Only in `X` (for namespaces, also inline namespaces and using-directives) |
| Where is an unqualified `f` looked up | Inside out, stopping at the first scope that has `f`; all outer scopes are hidden |
| When ADL is performed | Unqualified, unparenthesized function calls where ordinary lookup didn't find a class member, a block-scope function declaration or a non-function |
| Where ADL looks | The associated namespaces of the argument types, including those brought by template arguments, base classes and enclosing classes; plus friends of associated classes |
| Hidden friends | Found only through ADL; small overload sets, not picked through implicit conversions |
| Operators | Member candidates + non-member candidates (unqualified lookup ignoring members, plus ADL) + built-in candidates |
| Swapping in generic code | `std::ranges::swap(a, b)`, or `using std::swap; swap(a, b);` |
| What may be added to std | Only explicitly permitted cases such as class template specializations depending on your own types; everything else is UB |
