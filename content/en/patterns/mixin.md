---
title: Mixins
summary: "Building a class out of several unrelated, reusable small classes through inheritance: CRTP-style mixins parameterized on the derived class and layered mixins parameterized on the base class, how constructors pass through the layers, resolving name clashes, size under the empty base optimization, the overloaded idiom, and which mixins deducing this can replace."
tags: mixin, inheritance, CRTP, inherited constructors, empty base optimization, deducing this, pattern
updated: 2026-10-19
---

!!! tldr
    - A mixin is a small class that provides one capability and is combined into the target class through inheritance. Mixins taking the derived class as their template argument are mixins from above (CRTP-style); mixins taking the base class as their template argument are mixins from below (layered), and in the latter the order of the layers determines the behavior.
    - Layered mixins intercept calls through name hiding and inherit constructors with `using Base::Base;`. Each layer's own data members must have default member initializers, or the inherited constructors will not initialize them.
    - When two mixins have members with the same name, member name lookup reports an ambiguity before overload resolution, even if the parameter lists differ. A using-declaration in the derived class that brings both into the same scope fixes it.
    - An empty mixin base usually takes no space, but two empty base class subobjects of the same type must have different addresses and cost extra bytes. `overloaded` is the most common combination of empty mixins.
    - C++23's deducing this can replace mixins that only need to access the derived class. It cannot replace mixins that need per-derived-class state or that must spell the derived type in a signature.

## Three unrelated capabilities

A 2D point type needs three things: comparison with `!=`, printing itself, and counting how many instances currently exist. The three are unrelated to each other, and many other classes will need them too.

Writing them by hand in every class means repetition everywhere. A virtual interface doesn't fit either: `!=` takes two parameters of the concrete type, counting requires a counter per class, and virtual functions add a vptr to every object.

The **mixin** approach writes each capability as an independent small class, and the target class inherits from them to acquire their members. The inheritance here is for code reuse; it does not mean the target class is a kind of mixin. Depending on how the small class learns about the target class, there are two directions:

| | Syntax | What the small class knows | Typical use |
|---|---|---|---|
| Mixin from above | `struct Point : Printable<Point>` | the derived class's type | generating new members from members the derived class already has |
| Mixin from below | `Logging<Stack>` | the base class's type | wrapping members the base already has with an extra layer of behavior |

## From above: the derived class as the template argument

```cpp run title="above.cpp" ok
#include <cstdio>
#include <string>

template<class D>
struct Equality {
  friend bool operator!=(const D& a, const D& b) {
    return !(a == b);
  }
};

template<class D>
struct Printable {
  void print() const {
    const D& self = static_cast<const D&>(*this);
    std::printf("%s\n", self.to_string().c_str());
  }
};

template<class D>
struct Counted {
  static inline int alive = 0;
  Counted() { ++alive; }
  Counted(const Counted&) { ++alive; }
  ~Counted() { --alive; }
};

struct Point : Equality<Point>, Printable<Point>,
               Counted<Point> {
  int x = 0, y = 0;
  Point(int x, int y) : x(x), y(y) {}
  friend bool operator==(const Point& a, const Point& b) {
    return a.x == b.x && a.y == b.y;
  }
  std::string to_string() const {
    return "(" + std::to_string(x) + ", " + std::to_string(y) + ")";
  }
};

int main() {
  Point a{1, 2}, b{3, 4};
  a.print();                                   // (1, 2)
  std::printf("%d\n", a != b);                 // 1
  std::printf("%d\n", Counted<Point>::alive);  // 2
}
```

Each mixin takes the derived class `D` as its template argument. This technique is called CRTP (the curiously recurring template pattern); its mechanics and variants are covered in [[patterns/crtp]]. Here we only look at which rule each of the three mixins relies on:

- `Printable` downcasts `*this` to `const D&` in a member function. As long as the object really is a base class subobject of a `D` object, the result refers to that `D` object ([[expr.static.cast#2]]). Member function definitions are instantiated only when called ([[temp.inst#3]]), by which time `D` is complete, so `D::to_string` can be used.
- `Equality` defines a hidden friend (a friend function declared only inside the class). Ordinary lookup cannot find it; only ADL finds it in the associated classes of the argument types; see [[topics/name-lookup-and-customization]]. The signature says `D`, so it matches only `Point`.
- `Counted<Point>` and `Counted<Line>` are two different classes, each with its own static member `alive`. Every derived class automatically gets its own counter, a direct benefit of passing the derived type as a template argument.

The standard library's `std::ranges::view_interface<D>` ([[view.interface.general]]) is this kind of mixin: the derived class only provides `begin()` and `end()`, and it fills in `empty()`, `operator bool`, `front()`, `size()` and other members. `std::enable_shared_from_this<T>` ([[util.smartptr.enab]]) is another.

Some mixins have been replaced by language features. From C++20, `a != b` is rewritten as `!(a == b)`, and `<`, `>` and the rest can come from a defaulted `operator<=>` ([[P1185R2]]), so comparison mixins like `Equality` are no longer needed:

<div class="compare" markdown="1">

```cpp
// C++17: a mixin supplies !=
struct P : Equality<P> {
  int x, y;
  friend bool operator==(
      const P&, const P&);
};
```

```cpp
// C++20: one defaulted ==
#include <compare>
struct P {
  int x, y;
  bool operator==(const P&) const
    = default;
  auto operator<=>(const P&) const
    = default;
};
```

</div>

## From below: the base class as the template argument

The other direction makes the mixin inherit from its template parameter. `Counting<B>` adds a counting layer on top of `B`, where `B` can be any class with a `push`:

```cpp run title="layers.cpp" ok
#include <cstdio>
#include <vector>

struct IntStack {
  std::vector<int> v;
  void push(int x) { v.push_back(x); }
  std::size_t size() const { return v.size(); }
};

template<class Base>
struct Counting : Base {
  int pushes = 0;
  void push(int x) { ++pushes; Base::push(x); }
};

template<class Base>
struct NonNegative : Base {
  void push(int x) {
    if (x < 0) return;          // reject negative numbers
    Base::push(x);
  }
};

template<class S>
void feed(S& s) { for (int x : {3, -1, 4, -1, 5}) s.push(x); }

int main() {
  Counting<NonNegative<IntStack>> a;   // count first, then filter
  NonNegative<Counting<IntStack>> b;   // filter first, then count
  feed(a); feed(b);
  std::printf("a: pushes=%d size=%zu\n", a.pushes, a.size());  // 5 3
  std::printf("b: pushes=%d size=%zu\n", b.pushes, b.size());  // 3 3
}
```

The two types are made of the same three parts but behave differently: `a` counts every call, `b` counts only calls that pass the filter. A call starts at the outermost layer and is passed inward layer by layer, so the order of the layers is the order of execution. This is different from the side-by-side mixins in the next section.

This technique relies on two lookup rules.

First, a `push` declared in the derived class hides the base's `push`. When a name is looked up in class `C`, if `C`'s own scope contains the name, lookup stops there and does not go into the bases ([[class.member.lookup#3]]). So `a.push(x)` finds the outermost `Counting::push`, and calling the next layer requires writing `Base::push`.

Second, `Base` is a **dependent base class** ([[g:dependent-base-class|dependent base class]]), a base whose type depends on a template parameter. Unqualified lookup in a template definition does not look into the scope of dependent base classes ([[class.member.lookup#4]]). So when a layer uses a member of its base, it must write `Base::` or `this->`:

```cpp title="dependent.cpp" error
#include <cstddef>
struct IntStack {
  void push(int) {}
  std::size_t size() const { return 0; }
};
template<class Base>
struct Bounded : Base {
  void push(int x) {
    if (size() < 8)          // error: members of a dependent base do not take part in unqualified lookup
      Base::push(x);
  }
};
int main() { Bounded<IntStack> b; b.push(1); }
```

Clang reports `use of undeclared identifier 'size'` already at the template definition. Changed to `this->size()`, the name becomes a dependent name and is looked up in `Base` at instantiation; see [[topics/two-phase-lookup]].

<details class="fine" markdown="1"><summary>Stacking layers in order with a metafunction</summary>

With many layers, `Counting<NonNegative<Locked<IntStack>>>` has to be read from the inside out. A metafunction can apply the layers from the inside out in the order written:

```cpp run title="compose.cpp" ok
#include <type_traits>
struct IntStack { void push(int) {} };
template<class B> struct Counting : B {};
template<class B> struct NonNegative : B {};

template<class Base, template<class> class... Layers>
struct compose { using type = Base; };

template<class Base, template<class> class L,
         template<class> class... Rest>
struct compose<Base, L, Rest...>
  : compose<L<Base>, Rest...> {};

template<class Base, template<class> class... Layers>
using compose_t = compose<Base, Layers...>::type;

static_assert(std::is_same_v<
  compose_t<IntStack, NonNegative, Counting>,
  Counting<NonNegative<IntStack>>>);
int main() {}
```

The resulting type is unchanged; error messages and debuggers still show the full nested name.

</details>

## How constructors pass through the layers

The bottom class often needs constructor arguments. Writing a forwarding constructor by hand in every layer is tedious, and C++11's **inherited constructors** ([[g:inherited-constructor|inherited constructor]]) solve this:

```cpp run title="inherit_ctor.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

struct Connection {
  std::string host; int port;
  Connection(std::string h, int p) : host(std::move(h)), port(p) {}
  explicit Connection(int p) : Connection("localhost", p) {}
};

template<class Base>
struct Retrying : Base {
  using Base::Base;           // inherit all of Base's constructors
  int max_retries = 3;        // must have a default member initializer
};

template<class Base>
struct Timed : Base {
  using Base::Base;
  long timeout_ms = 1000;
};

int main() {
  Timed<Retrying<Connection>> c("example.org", 443);
  Timed<Retrying<Connection>> d(8080);
  auto e = c;                 // the copy constructor is implicitly declared, not inherited
  std::printf("%s:%d retries=%d timeout=%ld\n",
              e.host.c_str(), e.port, e.max_retries, e.timeout_ms);
  std::printf("%s:%d\n", d.host.c_str(), d.port);
}
```

It prints `example.org:443 retries=3 timeout=1000` and `localhost:8080`.

¶2: if a using-declaration names a constructor, the derived class **inherits** that set of base constructors ([[namespace.udecl#2]]). ¶13 says that when looking up the derived class's constructors or forming a set of overload candidates, they are treated as constructors of the derived class ([[namespace.udecl#13]]). `Retrying` inherits `Connection`'s two constructors, and `Timed` inherits them again from `Retrying`, so two layers out the object can still be constructed with `("example.org", 443)`. This is the model after the C++17 rewrite by [[P0136R1]]: the C++11 and C++14 wording implicitly declared a set of corresponding constructors in the derived class, whereas now the base's constructors take part in lookup directly.

When an inherited constructor is used for initialization, the rest of the object is initialized as if by a defaulted default constructor: only the base subobject it came from calls that constructor, and the other bases and data members are default-initialized ([[class.inhctor.init#1]]). That is why `max_retries` and `timeout_ms` in each layer get their values from their default member initializers. An `int` member without an initializer is not initialized at all, which is the easiest thing to miss with layered mixins.

Inherited constructors keep their properties. `Connection(int)` is `explicit`, so `Timed<Retrying<Connection>> d = 8080;` is ill-formed as well. Copy and move constructors are effectively not inherited: when there is exactly one argument whose type is related to the derived class, inherited copy and move constructors are excluded from the candidate set ([[over.match.funcs.general#9]]), and the derived class uses its own implicitly declared versions.

!!! pitfall "Don't replace `using Base::Base` with a catch-all forwarding constructor"
    Without inherited constructors, a common approach is a variadic template constructor that perfectly forwards every argument to the base. When copying, it gets selected ahead of the copy constructor:
    ```cpp run title="forwarding.cpp" ok
    #include <cstdio>
    #include <utility>

    struct Base { int id = 0; Base(int i) : id(i) {} };

    template<class B>
    struct Counting : B {
      template<class... A>
      Counting(A&&... a) : B(std::forward<A>(a)...) {}
      int calls = 0;
    };

    int main() {
      Counting<Base> x(7);
      x.calls = 5;
      Counting<Base> y = x;   // the template is chosen, not the copy constructor
      std::printf("id=%d calls=%d\n", y.id, y.calls);   // id=7 calls=0
    }
    ```
    `x` is a non-const lvalue, and the `Counting(Counting&)` instantiated from the template is a better match than the implicit `Counting(const Counting&)`. It forwards `x` to `Base`'s copy constructor, and this layer's `calls` is reinitialized to 0. The program is well-formed, but the result is wrong. Inherited constructors don't have this problem.

## Variadic mixins

The number of mixins from above can be left to the user. Write them as a template template parameter pack and expand it in the base-specifier list:

```cpp run title="variadic.cpp" ok
#include <cstdio>

template<class D>
struct Named {
  const char* name() const { return static_cast<const D&>(*this).tag; }
};

template<class D>
struct Greeter {
  void greet() const {
    std::printf("hello, %s\n", static_cast<const D&>(*this).name());
  }
};

template<template<class> class... Skills>
struct Robot : Skills<Robot<Skills...>>... {
  const char* tag = "R2";
};

int main() {
  Robot<Named, Greeter> r;
  r.greet();                                   // hello, R2
  static_assert(sizeof(r) == sizeof(const char*));
}
```

A base-specifier followed by `...` is a **pack expansion** ([[g:pack-expansion|pack expansion]], [[class.derived.general#4]]), and each element becomes a direct base class.

The base-specifier must say `Robot<Skills...>`, not just `Robot`. The class scope starts only at the member-specification ([[basic.scope.class#1]]); the base list is not part of it, so the **injected-class-name** ([[g:injected-class-name|injected-class-name]]), the name by which a class refers to itself from inside, is not visible there. With `Skills<Robot>...`, `Robot` means the class template itself, and Clang reports `use of class template 'Robot' requires template arguments`.

These bases sit side by side, with no forwarding between them. Which one is called is decided by name lookup, and there is no layer order as in the previous section. Order affects only construction and destruction: direct bases are initialized in the order of the base list ([[class.base.init#15.2]]) and destroyed in reverse.

[[class.mi#3]] forbids the same class from appearing twice as a direct base, so `Robot<Named, Named>` is ill-formed.

## Name clashes

Two mixins both provide `dump`: one outputs JSON and takes an indentation argument, the other outputs XML and takes none:

```cpp title="clash.cpp" error
#include <string>
template<class D> struct JsonDump {
  std::string dump(int) const { return "{}"; }
};
template<class D> struct XmlDump {
  std::string dump() const { return "<x/>"; }
};
struct Doc : JsonDump<Doc>, XmlDump<Doc> {};
int main() {
  Doc d;
  d.dump();     // error: dump found in both bases; lookup is ambiguous
}
```

The parameter lists are clearly different, yet the call is ill-formed. The reason is that member name lookup happens before overload resolution and looks only at names. `Doc` has no `dump` of its own, so lookup goes into both bases and gets two different declaration sets. When merging them, the declaration sets differ, and the result is an invalid set ([[class.member.lookup#5.2]]); if lookup yields an invalid set, the program is ill-formed ([[class.member.lookup#6]]). Overload resolution never gets a chance to run.

The fix is a using-declaration in the derived class that makes both `dump`s declarations in `Doc`'s scope. Lookup then finds them in `Doc` and doesn't go into the bases:

```cpp run title="clash_fixed.cpp" ok
#include <cstdio>
#include <string>
template<class D> struct JsonDump {
  std::string dump(int indent) const { return "{" + std::to_string(indent) + "}"; }
};
template<class D> struct XmlDump {
  std::string dump() const { return "<x/>"; }
};
struct Doc : JsonDump<Doc>, XmlDump<Doc> {
  using JsonDump::dump;      // both dumps become declarations in Doc's scope
  using XmlDump::dump;
};
int main() {
  Doc d;
  std::printf("%s %s\n", d.dump().c_str(), d.dump(2).c_str());  // <x/> {2}
}
```

For overload resolution, functions introduced by a using-declaration are treated as direct members of the derived class ([[namespace.udecl#12]]). The two `dump`s have different signatures and overload normally.

In the variadic case, using-declarations can be expanded too: `using Skills<Robot>::dump...;` ([[P0195R2]], C++17).

A using-declaration cannot resolve another kind of ambiguity: when the same base class appears twice along two paths, the using-declaration designates a member of the base, not a particular subobject, so it cannot pick one of them ([[namespace.udecl#15]]). That case can only be fixed by changing the inheritance structure, or by explicitly converting to one of the paths at the call site.

## overloaded: a mixin built from lambdas

The most common combination of mixins merges several lambdas into one overload set to pass to `std::visit`, the **overload pattern** ([[g:overload-pattern|overload pattern]]):

```cpp run title="overloaded.cpp" ok
#include <cstdio>
#include <string>
#include <variant>

template<class... Ts>
struct overloaded : Ts... {
  using Ts::operator()...;
};

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto f = overloaded{
    [](int i)                { std::printf("int %d\n", i); },
    [](double d)             { std::printf("double %g\n", d); },
    [](const std::string& s) { std::printf("string %s\n", s.c_str()); },
  };
  std::visit(f, v);                              // double 3.5
  static_assert(sizeof(f) == 1);
}
```

Each lambda is a class (a closure type; see [[topics/lambdas]]), and `overloaded` inherits from them: a mixin parameterized on its bases, except that the layers are side by side and don't forward to each other. These three lines rely on four rules:

| Syntax | Rule relied on |
|---|---|
| `: Ts...` | pack expansion in the base-specifier list ([[class.derived.general#4]]) |
| `using Ts::operator()...;` | pack expansion in a using-declaration ([[P0195R2]]); otherwise lookup of `operator()` is ambiguous, for the reason in the previous section |
| `overloaded{l1, l2, l3}` | a class with base classes can still be an aggregate, and its bases are its first elements ([[dcl.init.aggr#1]], [[dcl.init.aggr#2]], [[P0017R1]]) |
| No template arguments written | from C++20, template arguments of an aggregate class template can be deduced from a braced initializer ([[over.match.class.deduct#1]], [[P1816R0]]) |

C++17 has no class template argument deduction for aggregates and needs a deduction guide, `template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;`. Clang 23 compiling the code above with `-std=c++17` reports `no viable constructor or deduction guide`.

None of the three lambdas captures anything, so they are empty classes and `sizeof(f)` is 1. If each captured one variable by reference, we measured `sizeof(f)` as 16, i.e. two pointers; the empty base optimization applies to each closure base just the same. How the dispatch works is covered in [[patterns/visitor]].

## Empty base optimization: how much space mixins take

Most mixins have no data members and only contribute member functions. In the C++ object model a complete object occupies at least 1 byte, but a **potentially-overlapping subobject** ([[g:potentially-overlapping-subobject|potentially-overlapping subobject]]) can have zero size. Base class subobjects are potentially-overlapping subobjects ([[intro.object#7]]); a standard-layout class with no non-static data members used as a base is specified outright to have zero size ([[intro.object#8]]). This is the **empty base optimization** (EBO), and it makes mixins almost free in space.

But the address rules have an exception. One of the conditions under which two subobjects may share an address is that at least one has zero size and their types are not similar ([[intro.object#10.3]]). Two subobjects of the same type must have different addresses. Several mixins sharing one empty tag base run into this rule:

```cpp run title="ebo.cpp" impl
#include <cstdio>
struct Tag {};
template<class D> struct M1 {};
template<class D> struct M2 {};
template<class D> struct M3 {};
template<class D> struct T1 : Tag {};   // three mixins sharing Tag
template<class D> struct T2 : Tag {};
template<class D> struct T3 : Tag {};

struct A : M1<A>, M2<A>, M3<A> { int x; };
struct B : M1<B>, M2<B>, M3<B> {};
struct N : T1<N>, T2<N>, T3<N> {};
struct C : T1<C>, T2<C> { int x; };
struct K : T1<K>, T2<K> { char c; };
struct L : M1<L>, M2<L> { char c; };
struct E : Tag { Tag t; int x; };
struct F : Tag { [[no_unique_address]] Tag t; int x; };

int main() {
  std::printf("A=%zu B=%zu N=%zu C=%zu K=%zu L=%zu E=%zu F=%zu\n",
              sizeof(A), sizeof(B), sizeof(N), sizeof(C),
              sizeof(K), sizeof(L), sizeof(E), sizeof(F));
}
```

Results with Clang 23 (arm64, Itanium ABI), with offsets from `-Xclang -fdump-record-layouts`:

| Class | Composition | `sizeof` | Notes |
|---|---|---|---|
| `A` | three different empty mixins + `int` | 4 | all three bases at offset 0, sharing the address of `x` |
| `B` | three different empty mixins | 1 | a complete object is at least 1 byte |
| `N` | three mixins, each containing a `Tag` | 3 | the three `Tag`s must be at different addresses: offsets 0, 1, 2 |
| `C` | two mixins containing `Tag` + `int` | 4 | the second `Tag` is at offset 1, inside the bytes of `x`, taking no extra space |
| `K` | two mixins containing `Tag` + `char` | 2 | the second `Tag` is at offset 1; the `char` is only 1 byte, so 1 extra byte |
| `L` | two different empty mixins + `char` | 1 | control |
| `E` | empty base `Tag` + a `Tag` member + `int` | 8 | member `t` cannot share the base's address, goes to offset 1, and `x` has to align to 4 |
| `F` | same, with the member marked `[[no_unique_address]]` | 4 | `t` is still at offset 1, but may overlap `x` |

Empty subobjects of the same type do not necessarily cost space: if there is a large enough data member of a different type afterwards, they can fall inside its bytes (`C`, `F`). The cost appears when the class itself is nearly empty or its data is small (`N`, `K`), which is exactly the case for stateless policy objects and tag types.

Bases of the same type also make a class lose **standard layout** ([[g:standard-layout-class|standard-layout class]]): a standard-layout class has at most one base class subobject of any given type ([[class.prop#2.5]]). In our tests `std::is_standard_layout_v` is true for `A` and false for `C` and `E`.

!!! impl "MSVC and multiple empty bases"
    The above is the behavior of the Itanium C++ ABI (used by GCC and Clang on Linux and macOS). According to Microsoft's documentation, MSVC by default applies the empty base optimization only to the first empty base; with several empty bases, the class needs `__declspec(empty_bases)` for all of them to be compressed. It also ignores `[[no_unique_address]]` and offers `[[msvc::no_unique_address]]` instead. We could not verify MSVC; cross-platform libraries need to measure separately.

If you'd rather not inherit, a mixin can become a `[[no_unique_address]]` member instead ([[dcl.attr.nouniqueaddr]]), which can also have zero size. But a member doesn't bring its member functions into the class's interface, so you have to write forwarding functions by hand, which is exactly what mixins are meant to avoid. More layout details are in [[toolchain/object-layout-and-vtables]].

## deducing this: mixins without a template parameter

C++23's **explicit object parameters** ([[g:explicit-object-parameter|explicit object parameter]], [[dcl.fct#8]], [[P0847R7]]) let a member function take the object it is called on as its first parameter, with the type deduced. Many CRTP-style mixins therefore no longer need a template parameter:

<div class="compare" markdown="1">

```cpp
// CRTP: the base must know D
template<class D>
struct Printable {
  void print() const {
    auto& self =
      static_cast<const D&>(*this);
    puts(self.str().c_str());
  }
};
struct Point : Printable<Point> {
  std::string str() const;
};
```

```cpp
// C++23: self's type is deduced
struct Printable {
  void print(this const auto& self)
  {
    puts(self.str().c_str());
  }
};

struct Point : Printable {
  std::string str() const;
};
```

</div>

What is deduced is the static type of the object in the call expression. That brings one benefit and one limitation:

```cpp run title="deducing_this.cpp" ok
#include <cstdio>
#include <string>

struct Printable {                       // no longer a template
  void print(this const auto& self) {
    std::printf("%s\n", self.to_string().c_str());
  }
};

struct Point : Printable {
  int x = 1, y = 2;
  std::string to_string() const {
    return std::to_string(x) + "," + std::to_string(y);
  }
};

struct Point3 : Point {
  int z = 3;
  std::string to_string() const {
    return Point::to_string() + "," + std::to_string(z);
  }
};

int main() {
  Point3 p;
  p.print();                         // 1,2,3: self deduced as Point3
  const Point& r = p;
  r.print();                         // 1,2: self deduced as Point
}
```

The benefit is that `Point3`, one more level down, still gets its own `to_string`. In the CRTP version, `Printable<Point>` fixes `D` as `Point`, and `Point3` calling `print` would only print `1,2`. The limitation is that when `print` is called through a `const Printable&`, `self` is a `Printable`, `to_string` cannot be found, and instantiation fails.

deducing this cannot replace every mixin from above:

| The mixin needs | CRTP | deducing this |
|---|---|---|
| Access to derived members in member functions | yes | yes, and it also works for deeper derived classes |
| Per-derived-class static state (`Counted<D>`) | yes | no: there is only one base, so only one copy of the static member |
| The derived type spelled in a signature (`operator!=(const D&, const D&)`) | yes | no: a non-member function has no object parameter to deduce |
| Code run on construction and destruction | yes | yes, but without knowing the derived type |
| Member functions that are not templates | yes | no: instantiated once per calling type, must live in headers |

## Costs

At run time, layered mixins are just statically bound function calls, identical to hand-written code after inlining. Compiling the earlier `Counting<NonNegative<IntStack>>::push` and an equivalent hand-written function (count, check the sign, write to the array) separately at `-O2`, the arm64 instructions were identical one for one in our tests, 9 in total.

The costs are in compile time and readability. Each combination is a new set of template specializations, and each layer's member functions are instantiated separately. Type names grow with the number of layers: a `push` wrapped five layers deep has a mangled name of 131 characters in our tests, which demangles to:

```text
void Locked<Logging<NonEmpty<Counting<Stack<std::string>>>>>::push<std::string>(std::string)
```

(libc++'s `std::string` further expands to `std::__1::basic_string<char, ...>`.) Error messages also pass through every layer. Below, each layer forwards with an `auto` parameter; passing the wrong type:

```cpp title="deep_error.cpp" error
#include <string>
#include <vector>
template<class T> struct Stack { std::vector<T> v; void push(T x) { v.push_back(std::move(x)); } };
template<class B> struct Counting : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct NonEmpty : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct Logging : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct Locked : B { void push(auto x) { B::push(std::move(x)); } };
using S = Locked<Logging<NonEmpty<Counting<Stack<std::string>>>>>;
void use(S& s) { s.push(42); }   // error: int cannot be converted to std::string
```

Clang 23 reports the error in the innermost `Counting::push`, followed by four `in instantiation of function template specialization ...` notes, each with a full nested type name; the whole diagnostic is 40 lines. If each layer's `push` used a concrete parameter type, the error would appear right at the call site. Stepping into `s.push` in a debugger also passes through every layer in turn.

## Traps

### Self-calls within a layer bypass the outer layers

Layered mixins have no virtual functions, so when the bottom class calls its own member, it calls the bottom version:

```cpp run title="self_call.cpp" ok
#include <cstdio>
#include <initializer_list>
#include <vector>

struct IntStack {
  std::vector<int> v;
  void push(int x) { v.push_back(x); }
  void push_all(std::initializer_list<int> xs) {
    for (int x : xs) push(x);        // calls IntStack::push
  }
};

template<class Base>
struct NonNegative : Base {
  void push(int x) { if (x >= 0) Base::push(x); }
};

int main() {
  NonNegative<IntStack> s;
  s.push(-1);              // filtered
  s.push_all({-2, -3});    // bypasses the filtering layer
  std::printf("%zu\n", s.v.size());   // 2
}
```

An outer layer can only intercept calls made from outside through the outer type. If the bottom layer needs to call back into the outermost one, it must know the outermost type, which brings you back to CRTP or deducing this.

### Converting to the base also bypasses the outer layers

`NonNegative<IntStack>` converts implicitly to `IntStack&`, and once passed to a function taking `IntStack&`, none of the filtering applies. If you don't want that, use `protected` or `private` inheritance and expose the needed members with using-declarations.

### This layer's data members have no initializer

Inherited constructors don't initialize them; see above.

### Empty bases of the same type

Several mixins inheriting the same tag class take extra space and lose standard layout; see the table above.

## When to use them

| Situation | Recommendation |
|---|---|
| Completing a set of interfaces from members the derived class already has (e.g. `view_interface`) | a mixin from above; when it only needs access to derived members, C++23 can use deducing this instead |
| Each derived class needs separate static state, or friends taking the derived type as a parameter | a mixin from above (CRTP) |
| Adding checks, counting, locking or logging around the operations of an existing class | layered mixins from below; mind the order and self-calls |
| Which behaviors to add is decided at run time | not a fit for mixins; use decorators or callback objects (run-time composition) |
| The things being combined are different implementations of the same responsibility (allocation, threading model, error handling) | see [[patterns/policy-based-design\|policy-based design]], which also often uses inheritance to carry policies |
| Just comparison operators | C++20 defaulted `==` and `<=>`, no mixin needed |
| Merging several function objects into one overload set | `overloaded` |

## Questions

!!! question "Why does a `using` declaration resolve the `dump` ambiguity but not the one below?"
    ```cpp
    struct Base { void f(); };
    template<class D> struct M1 : Base {};
    template<class D> struct M2 : Base {};
    struct X : M1<X>, M2<X> { using Base::f; };
    void g(X& x) { x.f(); }
    ```

<details markdown="1">
<summary>Answer</summary>

The two `dump` declarations come from different classes. Once the using-declarations bring them into `X`'s scope, lookup ends in `X` with two functions that can be overloaded.

Here there is only one declaration, `Base::f`; the problem is that `X` contains two `Base` subobjects. A using-declaration designates a member of the base, not a particular subobject (note in [[namespace.udecl#15]]), and the call still has to convert `x` to `Base&` as the object argument, a conversion that is ambiguous. Clang reports `ambiguous conversion from derived class 'X' to base class 'Base'`. Writing `using M1<X>::f;` changes nothing; it still designates `Base::f`.

There are three workable fixes: define `void f() { M1<X>::f(); }` in `X`, where the qualified name says which subobject to go through; write `static_cast<M1<X>&>(x).f()` at the call site; or make `M1` and `M2` inherit `Base` virtually, so `X` has only one `Base` subobject.

</details>

!!! question "What is missing from `Logged` below? What is the value of `w.count` after `Logged<Widget> w(42);`?"
    ```cpp
    struct Widget { explicit Widget(int); };
    template<class B> struct Logged : B {
      using B::B;
      int count;
    };
    ```

<details markdown="1">
<summary>Answer</summary>

`count` has no default member initializer. When `Logged<Widget>` is initialized with the inherited `Widget(int)`, everything except the `Widget` base subobject is initialized as if by a defaulted default constructor ([[class.inhctor.init#1]]), so the `int` is default-initialized, meaning no initialization is performed. If `w` has automatic storage duration, reading `w.count` yields an erroneous value in C++26, which is erroneous behavior; before C++26 it is UB. Write `int count = 0;`.

</details>

!!! question "Why doesn't `template<template<class> class... Ms> struct X : Ms<X>... {};` compile?"

<details markdown="1">
<summary>Answer</summary>

The base list is not within the class scope of `X` ([[basic.scope.class#1]]), so looking up `X` there does not find the injected-class-name, only the class template `X` itself. A class template name without arguments cannot be used as a type, so you have to write `Ms<X<Ms...>>...`. Only inside the class body does `X` refer to the current specialization.

</details>
