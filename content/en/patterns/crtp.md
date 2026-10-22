---
title: CRTP and static polymorphism
summary: "A derived class passes itself as the template argument of its base (class D : public Base<D>): why this compiles, why static_cast<D&>(*this) is safe, how it differs from virtual functions in code generation and object size, where the standard library uses it, the common traps, and which of its uses C++23's explicit object parameters replace."
tags: CRTP, static polymorphism, templates, deducing this, idiom
updated: 2026-10-19
---

!!! tldr
    - CRTP makes a base class template take the derived class as its argument: `class D : public Base<D>`. The base gets the derived object in its member functions with `static_cast<D&>(*this)`, and which function is called is fixed at compile time.
    - It compiles because instantiating a class template generates only the declarations of its member functions. Function bodies are instantiated when they are used, and by then `D` is complete. Conversely, the base's member declarations (member types, parameter and return types) cannot use members of `D`.
    - Compared with virtual functions, CRTP has no vptr and calls can be inlined. The cost is that there is no common base type, objects of different derived classes cannot go in the same container, and each `D` gets its own copy of the code.
    - With the wrong template argument (`class E : public Base<D>`) the `static_cast` is undefined behavior and the compiler says nothing. Making the base constructor private and declaring `friend D` turns this into a compile error.
    - C++23's explicit object parameters (deducing this) replace CRTP that exists only to call members of the derived class. CRTP is still needed for per-derived-class static data, for non-member operators taking `D` as a parameter, and for keeping `D` when calling through a base reference.

## The base class wants to call the derived class

Several shapes share some printing logic and differ only in how the area is computed. The usual approach makes the area a virtual function:

<div class="compare" markdown="1">

```cpp
struct Shape {
  virtual double area() const = 0;
  void print() const {
    std::printf("%.2f\n", area());
  }
protected:
  ~Shape() = default;
};

struct Square : Shape {
  double s = 2;
  double area() const override {
    return s * s;
  }
};
```

```cpp
template<class D>
struct Shape {
  void print() const {
    auto& d = static_cast<const D&>(*this);
    std::printf("%.2f\n", d.area());
  }
protected:
  ~Shape() = default;
};

struct Square : Shape<Square> {
  double s = 2;
  double area() const { return s * s; }
};
```

</div>

On the left, every `Square` object carries a pointer to a virtual function table (the vptr), and `print` calls `area` indirectly through it. If every call site in the program knows the concrete type of the object, and the base exists only to share code, this run-time dispatch is wasted.

On the right, the base is a template, and the derived class passes itself in as the template argument. `Shape<Square>::print` knows that `*this` is really a base class subobject of a `Square`, converts it to `const Square&`, and calls `Square::area` directly. This is called **CRTP** (the curiously recurring template pattern).

Which function is called is decided when the template is instantiated. This is **static polymorphism**; virtual functions choose the function at run time from the object's dynamic type, which is dynamic polymorphism. Here is a complete program:

```cpp run title="crtp-shape.cpp" ok
#include <cstdio>

template<class D>
class Shape {
public:
  double area() const {                      // public interface
    return self().area_impl();               // forwards to the derived implementation
  }
  void print() const {
    std::printf("%s: %.2f\n", self().name(), area());
  }
protected:
  Shape() = default;
  ~Shape() = default;
private:
  const D& self() const { return static_cast<const D&>(*this); }
};

class Square : public Shape<Square> {
  double s_;
public:
  explicit Square(double s) : s_(s) {}
  double area_impl() const { return s_ * s_; }
  const char* name() const { return "square"; }
};

class Circle : public Shape<Circle> {
  double r_;
public:
  explicit Circle(double r) : r_(r) {}
  double area_impl() const { return 3.14159 * r_ * r_; }
  const char* name() const { return "circle"; }
};

template<class D>
void report(const Shape<D>& s) { s.print(); }

int main() {
  report(Square{2});                         // square: 4.00
  report(Circle{1});                         // circle: 3.14
  static_assert(sizeof(Square) == sizeof(double));
}
```

`Shape<Square>` and `Shape<Circle>` are two unrelated classes. `report` is a function template, and each instance knows the concrete type of its parameter. The base has no data members and as an empty base takes no space, so a `Square` is the size of one `double`.

The interface function `area` and the implementation function `area_impl` have different names, and the constructor and destructor are `protected`. The reasons for both are in the traps section below.

## Why it compiles

At the line `class Square : public Shape<Square>`, the definition of `Square` has not ended yet, so it is an incomplete type ([[g:incomplete-type]]). A base class must be a complete class ([[class.derived.general#2]]), so the compiler implicitly instantiates `Shape<Square>` here ([[temp.inst#2]]), while `D` is incomplete.

Implicit instantiation of a class template specialization generates only the declarations of member functions, not their definitions ([[temp.inst#3]]). The definition of a non-virtual member function is instantiated only when it is needed ([[temp.inst#12]]). So when `Shape<Square>` is instantiated, `area`, `print` and `self` exist only as declarations, and the `static_cast<const D&>` in their bodies has not been checked yet.

Only when `main` calls `print` is the definition of `Shape<Square>::print` needed. Its point of instantiation ([[g:point-of-instantiation]]) immediately follows the namespace-scope declaration that refers to it, here the definition of `main` ([[temp.point#1]]); the end of the translation unit is also a point of instantiation for it ([[temp.point#7]]). Both are after the definition of `Square`, so `Square` is complete, and both the `static_cast` and the call to `area_impl` succeed.

!!! note "This has nothing to do with the complete-class context"
    A member function body is a complete-class context of its class ([[g:complete-class-context]], [[class.mem.general#10]]), within which the class is regarded as complete ([[class.mem.general#11]]). This rule lets the member function bodies of `Shape` use members of `Shape` declared later, but it is about `Shape` itself, not about `D`. `D` is complete inside the function body purely because the body is instantiated only after `D` is defined.

### The base's declarations cannot use members of D

Function bodies are instantiated late, but member declarations are not. A base that wants to use a member type of the derived class fails:

```cpp title="member-type.cpp" error
#include <vector>

template<class D>
struct Container {
  using value_type = typename D::value_type;   // error
  value_type first() const {
    return static_cast<const D&>(*this).data().front();
  }
};

struct IntBag : Container<IntBag> {
  using value_type = int;
  std::vector<int> v{1, 2, 3};
  const std::vector<int>& data() const { return v; }
};
```

Clang 23 reports `no type named 'value_type' in 'IntBag'` and points to the line `struct IntBag : Container<IntBag>` as the origin of the instantiation. `Container<IntBag>` is instantiated in `IntBag`'s base list; a lookup in the class scope of `IntBag` at that point only finds members already declared, and there are none yet (see the same example in [[basic.scope]]).

Parameter and return types of member functions are also part of declarations, so writing `typename D::value_type first() const` fails too. There are three common workarounds:

```cpp run title="deferred-types.cpp" ok
#include <vector>

template<class D>
struct Container {
  auto first() const {                        // return type deduced when the body is instantiated
    return static_cast<const D&>(*this).data().front();
  }
  template<class Self = D>
  typename Self::value_type second() const {  // substitution deferred until the call
    return static_cast<const Self&>(*this).data()[1];
  }
};

struct IntBag : Container<IntBag> {
  using value_type = int;
  std::vector<int> v{1, 2, 3};
  const std::vector<int>& data() const { return v; }
};

int main() { IntBag b; return b.first() + b.second(); }   // exit code 3
```

The first uses an `auto` return type, which is deduced only when the body is instantiated. The second makes the member a member template whose default argument is `D`, so `Self::value_type` in the declaration is substituted only at the call; the standard library's `view_interface::operator[]` is written this way ([[view.interface]]). The third declares a specialization of a traits class before `D`, and the base takes its types from the traits class instead of from `D`. That costs an extra specialization, but the member types can then be used at class level.

## Why the static_cast is safe

`static_cast<const D&>(*this)` is a downcast from base to derived. [[expr.static.cast#2]] allows an lvalue of type `B` to be converted to `D&` if `D` is a complete type, `B` is a non-virtual base of `D`, and the standard conversion from `D*` to `B*` is valid, meaning `B` is an accessible, unambiguous base. If the `B` object being converted really is a base class subobject of a `D` object, the result refers to that `D` object; otherwise the behavior is undefined.

!!! std
    If the object of type "cv1 B" is actually a base class subobject of an object of type D, the result refers to the enclosing object of type D. Otherwise, the behavior is undefined.

    The conversion itself performs no run-time check. As long as `Shape<D>` is inherited only by `D`, `*this` is always a subobject of some `D`, and the conversion is defined.

Unlike `dynamic_cast`, it reads no run-time information and does not require the class to be polymorphic. The compiler only needs to compute, at compile time, the offset of the base class subobject within `D`. With single inheritance the offset is usually 0 and the conversion generates no instructions; when the base is not at the start it is a subtraction of a constant:

```cpp title="offset.cpp" ok
struct Other { long x; };
template<class D> struct Base {
  long b;
  const D& self() const { return static_cast<const D&>(*this); }
};
struct D : Other, Base<D> { long d; };

const D& down(const Base<D>& b) { return b.self(); }
```

Clang 23 at `-O2` for x86-64 Linux generates `down` as just two instructions, `lea rax, [rdi - 8]` and `ret`.

## Compared with virtual functions: size and code generation

Write the same `area` once as a virtual function and once with CRTP, and compare the object sizes and a caller that is not inlined:

```cpp title="codegen.cpp" ok
struct VShape {
  virtual double area() const = 0;
  virtual ~VShape() = default;
};
struct VSquare final : VShape {
  double s;
  double area() const override { return s * s; }
};
double twice_v(const VShape& x) { return x.area() * 2; }

template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};
struct Square : Shape<Square> {
  double s;
  double area_impl() const { return s * s; }
};
template<class D>
double twice(const Shape<D>& x) { return x.area() * 2; }
template double twice(const Shape<Square>&);   // explicit instantiation, to inspect the assembly

static_assert(sizeof(VSquare) == 16);          // vptr + double (64-bit target in our tests)
static_assert(sizeof(Square) == 8);            // just the double
```

Clang 23, `-O2 -target x86_64-linux-gnu -masm=intel`:

<div class="compare" markdown="1">

```text
twice_v(VShape const&):
  push  rax
  mov   rax, qword ptr [rdi]   ; load the vptr
  call  qword ptr [rax]        ; indirect call
  addsd xmm0, xmm0
  pop   rax
  ret
```

```text
twice<Square>(Shape<Square> const&):
  movsd xmm0, qword ptr [rdi]
  mulsd xmm0, xmm0             ; inlined
  addsd xmm0, xmm0
  ret
```

</div>

The virtual version loads the vptr, then the table entry, then makes an indirect call, and the body of `area` cannot be inlined into the caller. In the CRTP version both `area` and `area_impl` are inlined, leaving one multiplication and one addition.

The difference exists only where the compiler does not know the dynamic type. Add `double local_v(double s) { VSquare q; q.s = s; return twice_v(q); }` to the same file: after inlining `twice_v`, Clang knows that `q` is a `VSquare`, devirtualizes the call, and generates code as short as the CRTP version. The same happens when the parameter is a reference to a `final` class. The layout of vptrs and virtual function tables is covered in [[toolchain/object-layout-and-vtables]].

CRTP pays elsewhere:

| | Virtual functions | CRTP |
|---|---|---|
| Object size | one extra vptr | unchanged (the empty base takes no space) |
| Calls | indirect, usually not inlinable | direct, inlinable |
| Common base type | yes, a `VShape&` can refer to any derived class | no, `Shape<Square>` and `Shape<Circle>` are unrelated |
| Heterogeneous containers | `vector<unique_ptr<VShape>>` | not directly; needs `variant` or type erasure |
| Users | ordinary functions, can live in a .cpp file | must be templates, defined in headers |
| Code size | one copy | one instantiation per `D` |
| Adding a derived class | users need not be recompiled | users must be re-instantiated |

When the concrete type is known only at run time, CRTP does not help; use virtual functions, `std::variant` or [[patterns/type-erasure]].

## Typical uses

### Generating the other operators from one

Before C++20, comparison operators had to be written one by one. A CRTP base can generate the others from a `<` provided by the derived class:

```cpp run title="ordered.cpp" ok
#include <cstdio>

template<class D>
struct Ordered {                       // derives the other comparisons from <
  friend bool operator> (const D& a, const D& b) { return b < a; }
  friend bool operator<=(const D& a, const D& b) { return !(b < a); }
  friend bool operator>=(const D& a, const D& b) { return !(a < b); }
  friend bool operator!=(const D& a, const D& b) { return a < b || b < a; }
};

struct Version : Ordered<Version> {
  int major, minor;
  Version(int ma, int mi) : major(ma), minor(mi) {}
  friend bool operator<(const Version& a, const Version& b) {
    return a.major < b.major || (a.major == b.major && a.minor < b.minor);
  }
};

int main() {
  Version a{1, 2}, b{1, 10};
  std::printf("%d %d %d\n", a < b, a >= b, a != b);   // 1 0 1
}
```

These operators are friend functions defined in the class, findable only through argument-dependent lookup ([[g:argument-dependent-lookup|ADL]]); such functions are called hidden friends ([[g:hidden-friend]]). `Version`'s base `Ordered<Version>` is one of its associated classes ([[basic.lookup.argdep#3.3]]), and friend functions of associated classes are visible to ADL ([[basic.lookup.argdep#4.2]]), so `a >= b` finds the `operator>=` in `Ordered<Version>`. Because the parameters are `const D&` rather than `const Ordered&`, both sides of a comparison must be the same derived class.

From C++20 this use is mostly replaced by a defaulted `<=>` ([[P0515R3]]):

```cpp run title="spaceship.cpp" ok
#include <compare>
#include <cstdio>

struct Version {
  int major, minor;
  auto operator<=>(const Version&) const = default;   // also implicitly declares ==
};

int main() {
  Version a{1, 2}, b{1, 10};
  std::printf("%d %d %d\n", a < b, a >= b, a != b);   // 1 0 1
}
```

A defaulted `<=>` implicitly declares a defaulted `==` ([[class.compare.default#4]]), and `a >= b` and `a != b` are handled by rewritten candidates; see [[class.compare]]. You only need to write `<=>` or `==` yourself when the comparison is not memberwise.

### Per-derived-class static data

```cpp run title="counted.cpp" ok
#include <cstdio>

template<class D>
class Counted {
  static inline int alive_ = 0;          // one each for Counted<Socket> and Counted<File>
protected:
  Counted() { ++alive_; }
  Counted(const Counted&) { ++alive_; }
  ~Counted() { --alive_; }
public:
  static int alive() { return alive_; }
};

struct Socket : Counted<Socket> {};
struct File   : Counted<File>   {};

int main() {
  Socket a, b;
  {
    File f;
    Socket c = a;
    std::printf("%d %d\n", Socket::alive(), File::alive());   // 3 1
  }
  std::printf("%d %d\n", Socket::alive(), File::alive());     // 2 0
}
```

Here the base does not use any member of `D` at all; `D` only serves to tell the classes apart. Each derived class gets a different base specialization, and therefore its own `alive_`. With an ordinary base class, all derived classes would share one counter.

### CRTP bases in the standard library

- `std::enable_shared_from_this<T>`: the derived class inherits `shared_from_this()` from it, which returns a `shared_ptr<T>` sharing ownership with existing `shared_ptr`s. The base needs `T` to spell the return type `shared_ptr<T>` ([[util.smartptr.enab]]).
- `std::ranges::view_interface<D>`: the derived class writes only `begin` and `end`, and the base provides `empty`, `operator bool`, `size`, `front`, `back`, `operator[]` and so on, depending on the iterator category ([[view.interface]]).
- `std::ranges::range_adaptor_closure<D>` ({{c++23}}, [[P2387R3]]): a function object that inherits from it can be applied to a range with `|` and composed with other adaptors ([[range.adaptor.object]]).

```cpp run title="std-crtp.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

class IntSpan : public std::ranges::view_interface<IntSpan> {
  int* first_ = nullptr;
  int* last_ = nullptr;
public:
  IntSpan() = default;
  IntSpan(int* f, int* l) : first_(f), last_(l) {}
  int* begin() const { return first_; }
  int* end() const { return last_; }
};

struct Doubled : std::ranges::range_adaptor_closure<Doubled> {
  auto operator()(std::ranges::viewable_range auto&& r) const {
    return std::views::transform(std::forward<decltype(r)>(r),
                                 [](int x) { return 2 * x; });
  }
};
inline constexpr Doubled doubled;

int main() {
  std::vector<int> v{1, 2, 3, 4};
  IntSpan s{v.data(), v.data() + v.size()};
  std::printf("%zu %d %d %d\n", s.size(), s.front(), s.back(), s[2]);  // 4 1 4 3
  for (int x : v | std::views::reverse | doubled)
    std::printf("%d ", x);                                             // 8 6 4 2
  std::puts("");
}
```

### A common implementation of a virtual function

CRTP can also work together with virtual functions. A polymorphic `clone` is written the same way in every derived class except for the type, so a CRTP class in the middle can provide it once:

```cpp run title="clone.cpp" ok
#include <cstdio>
#include <memory>

struct Animal {
  virtual ~Animal() = default;
  virtual std::unique_ptr<Animal> clone() const = 0;
  virtual const char* name() const = 0;
};

template<class D>
struct Clonable : Animal {
  std::unique_ptr<Animal> clone() const override {
    return std::make_unique<D>(static_cast<const D&>(*this));
  }
};

struct Cat : Clonable<Cat> {
  const char* name() const override { return "cat"; }
};
struct Dog : Clonable<Dog> {
  const char* name() const override { return "dog"; }
};

int main() {
  std::unique_ptr<Animal> a = std::make_unique<Dog>();
  std::puts(a->clone()->name());   // dog
}
```

<details class="fine" markdown="1"><summary>Point of instantiation of a virtual function</summary>

`Clonable<Cat>::clone` is a virtual function, and by [[temp.inst#12]] it is unspecified whether the implementation instantiates it when instantiating the class. By [[temp.point#5]], the point of instantiation of the virtual function immediately follows that of `Clonable<Cat>`, when `Cat` is still incomplete, yet both `static_cast<const D&>` and `make_unique<D>` in the body need a complete `D`. [[temp.point#7]] also counts the end of the translation unit as a point of instantiation, when `Cat` is complete. Clang 23 accepts the program and runs it correctly, and implementations generally instantiate such functions at the end of the translation unit, but the standard's wording is unclear for this case.

</details>

## Traps

### The wrong template argument

When copying and pasting a derived class, it is easy to forget to change the base's template argument:

```cpp run title="wrong-derived.cpp" ub
#include <cstdio>

template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

struct Circle : Shape<Square> {               // forgot to change it to Shape<Circle>
  double r = 1;
  double area_impl() const { return 3.14159 * r * r; }
};

int main() {
  Circle c;
  std::printf("%f\n", c.area());  // UB: *this is not a base class subobject of any Square
}
```

The program compiles, because `Square` really is publicly derived from `Shape<Square>`, so the conversion meets every compile-time condition in [[expr.static.cast#2]]. But the `Shape<Square>` subobject in `c` does not belong to any `Square` object, so the conversion has undefined behavior. In our tests it prints `1.000000`: `Square::area_impl` treats `Circle`'s `r` as `s`. UBSan reports nothing; its type checks only cover polymorphic classes.

Make the base constructor private and let only `D` be a friend, and the mistake is caught at compile time:

```cpp title="guard.cpp" error
template<class D>
class Shape {
public:
  double area() const { return static_cast<const D&>(*this).area_impl(); }
private:
  Shape() = default;
  friend D;                                   // only D can construct Shape<D>
};

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

struct Circle : Shape<Square> {
  double r = 1;
  double area_impl() const { return 3.14159 * r * r; }
};

int main() {
  Square s;                                   // OK
  Circle c;                                   // error
}
```

In `friend D;`, `D` is a template parameter; when it names a class type, that class becomes a friend ([[class.friend#3]]). `Circle`'s implicit default constructor has to call the private constructor of `Shape<Square>`, and `Circle` is not a friend of `Shape<Square>`, so that default constructor is defined as deleted. Clang 23 reports `call to implicitly-deleted default constructor of 'Circle'` at `Circle c;`, explaining that `base class 'Shape<Square>' has an inaccessible default constructor`. If `Circle` writes its own constructor, the error appears at that constructor's definition.

### Access to the constructor and destructor

A CRTP base is not meant to be instantiated on its own, so its constructor is usually `protected` (or private plus a friend, as in the previous section). The destructor should also be `protected` and non-virtual: the base has no virtual destructor, so deleting a `Square` through a `Shape<Square>*` is undefined behavior ([[expr.delete]]). With a `protected` destructor such a `delete` does not compile:

```cpp title="protected-dtor.cpp" error
template<class D>
struct Shape {
protected:
  ~Shape() = default;
};
struct Square : Shape<Square> { double s = 2; };

void destroy(Shape<Square>* p) { delete p; }   // error
```

Clang 23 reports `calling a protected destructor of class 'Shape<Square>'`.

A `protected` constructor has a side effect. A derived class without user-declared constructors is an aggregate ([[g:aggregate]]), and when it is initialized with `{}`, the base class subobject is initialized in the caller's context, which has no access to the `protected` constructor:

```cpp title="aggregate.cpp" error
template<class D>
class Shape {
protected:
  Shape() = default;
};
struct Square : Shape<Square> { double s = 2; };

int main() {
  Square a;          // OK: calls Square's implicit default constructor
  Square b{};        // error: aggregate initialization
}
```

Clang 23 reports `base class 'Shape<Square>' has protected default constructor` for `b`. Give the derived class a constructor and it is no longer an aggregate.

### The base is private

When the derived class is defined with `class`, its base is private by default:

```cpp title="private-base.cpp" error
template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

class Square : Shape<Square> {                // private inheritance
public:
  using Shape::area;
  double area_impl() const { return 4; }
};

int main() { return Square{}.area(); }
```

[[expr.static.cast#2]] requires a valid standard conversion from `D*` to `B*`, and a private base is not accessible in the members of `Shape<Square>` ([[class.access.base#4]]), so the conversion is ill-formed. Clang 23 reports `cannot cast private base class 'const Shape<Square>' to 'const Square'` inside the body of `Shape<Square>::area`, with a note that the instantiation comes from the call in `main`.

By the same reasoning, if the derived class makes `area_impl` private, the base cannot call it either, and the derived class needs `friend Shape;`. Here `Shape` is the injected-class-name ([[g:injected-class-name]]) inherited from the base and means `Shape<Square>`.

### Interface and implementation with the same name

If the base's interface function has the same name as the derived function it calls, and the derived class forgets to provide the implementation, name lookup finds the base's own function:

```cpp run title="recursion.cpp" ub
#include <cstdio>

template<class D>
struct Printable {
  void print() const { static_cast<const D&>(*this).print(); }  // interface and implementation share a name
};

struct Point : Printable<Point> {
  int x = 1, y = 2;
  // forgot to write print()
};

int main() { Point{}.print(); }
```

`Point` has no `print`, so `static_cast<const Point&>(*this).print()` finds the inherited `Printable<Point>::print`, and the function recurses forever. Infinite recursion without side effects violates the forward progress guarantee ([[intro.progress#1]]), so the behavior is undefined. Clang 23 issues a `-Winfinite-recursion` warning; at `-O0` the program crashes with a stack overflow, at `-O2` the process is killed by `SIGTRAP`.

With different names for interface and implementation (`area` and `area_impl`), a missing implementation is a compile error rather than infinite recursion at run time. It is the same idea as [[patterns/nvi|the non-virtual interface]] separating the public interface from the customizable part.

### Hiding is not overriding

When a derived class defines a function with the same name as one in the base, it hides the base function but does not override it. The result depends on where the call comes from:

```cpp run title="hiding.cpp" ok
#include <cstdio>

template<class D>
struct Widget {
  const char* name() const { return "widget"; }   // default implementation
  void show() const {
    std::printf("%s / %s\n",
                name(),                             // Widget::name
                static_cast<const D&>(*this).name());
  }
};

struct Button : Widget<Button> {
  const char* name() const { return "button"; }   // hides Widget::name
};

int main() {
  Button b;
  b.show();                        // widget / button
  const Widget<Button>& w = b;
  std::printf("%s\n", w.name());   // widget
  std::printf("%s\n", b.name());   // button
}
```

A plain `name()` in the base means `this->name()`; lookup starts in `Widget` and finds `Widget::name`. Only through `static_cast<const D&>(*this)` does lookup start in `Button` ([[class.member.lookup]]). Calling `name` through a `Widget<Button>&` works the same way. When CRTP provides default implementations, every call inside the base has to go through `self()`, or the default version is silently used.

The same holds with multiple levels of derivation. If `struct Tile : Square` defines another `area_impl`, calling `area()` on a `Tile` still goes through `Shape<Square>` and calls `Square::area_impl`, because the base only knows `Square`.

### Calling the derived class from the base constructor

The base constructor runs before the derived class's members are initialized. Calling a derived member function through `static_cast` at that point makes the function access members that have not been constructed yet:

```cpp run title="ctor-call.cpp" ub
#include <cstdio>
#include <string>

template<class D>
struct Registered {
  Registered() {
    std::printf("registering %s\n", static_cast<D&>(*this).key().c_str());
  }
};

struct Plugin : Registered<Plugin> {
  std::string name = "a-plugin-with-a-long-name";
  const std::string& key() const { return name; }
};

int main() { Plugin p; }   // UB: name has not been constructed yet
```

The `Plugin` object is under construction, and calling member functions on an object under construction is allowed ([[class.cdtor#4]]), so the call to `key()` itself is fine. The problem is that construction of `name` has not started, so its lifetime has not begun, and calling `c_str()` on it is undefined behavior ([[basic.life#8]]). In our tests it printed garbage, and neither ASan nor UBSan reported anything.

Virtual functions are at least defined here: a virtual call during construction lands on the version of the class under construction ([[class.cdtor#4]]) and never reaches the derived class. CRTP bypasses that protection, so base constructors and destructors should not call members of the derived class. Work that must wait until the derived class is fully constructed belongs in the derived class's own constructor, or should be called explicitly by the user after construction.

## C++23: explicit object parameters

C++23 lets a non-static member function spell its object parameter as an explicit first parameter ([[dcl.fct#7]], [[P0847R7]]). This is often called deducing this: make that parameter a template, and `Self` is deduced as the actual type of the object expression, so the base no longer needs to be a template.

<div class="compare" markdown="1">

```cpp
template<class D>
struct Shape {
  double area() const {
    return static_cast<const D&>(*this)
        .area_impl();
  }
};

struct Square : Shape<Square> {
  double s;
  double area_impl() const {
    return s * s;
  }
};
```

```cpp
struct Shape {
  template<class Self>
  double area(this const Self& self) {
    return self.area_impl();
  }
};

struct Square : Shape {
  double s;
  double area_impl() const {
    return s * s;
  }
};
```

</div>

On the right, calling `area()` on a `Square` deduces `Self` as `Square`, so `self` is a `const Square&`. No conversion is needed, so there is no wrong template argument and no private-base problem. Such a function is called an explicit object member function ([[g:explicit-object-member-function]], [[dcl.fct#8]]).

The difference is that `Self` is deduced from the static type at the call site. Called through a base reference, `Self` is the base:

```cpp run title="deducing-this.cpp" ok
#include <cstdio>

struct Shape {
  template<class Self>
  double area(this const Self& self) { return self.area_impl(); }
  template<class Self>
  void print(this const Self& self) {
    std::printf("%s: %.2f\n", self.name(), self.area());
  }
};

struct Square : Shape {
  double s;
  explicit Square(double s) : s(s) {}
  double area_impl() const { return s * s; }
  const char* name() const { return "square"; }
};

void report(const auto& s) { s.print(); }

int main() {
  Square q{2};
  q.print();                       // square: 4.00, Self = Square
  report(q);                       // square: 4.00
  [[maybe_unused]] const Shape& base = q;
  // base.print();                 // error: Self = Shape, and Shape has no name
}
```

Uncomment the last line and Clang 23 reports `no member named 'name' in 'Shape'`, from the instantiation of `Shape::print<Shape>`. CRTP's `const Shape<Square>&` still knows that `D` is `Square`; the explicit object parameter's `const Shape&` has lost that information.

With multiple levels of derivation the outcome is reversed. In the earlier `Tile : Square` example, the CRTP version calls `Square::area_impl`; with an explicit object parameter, `Tile{}.area()` deduces `Self = Tile` and calls `Tile::area_impl`. In our tests they return 4 and 5 respectively.

Explicit object parameters replace CRTP written only to get the derived type inside member functions. The following cases still need CRTP:

| Need | Why explicit object parameters can't do it |
|---|---|
| Per-derived-class static data (e.g. `Counted<D>`) | explicit object parameters exist only in member functions; there is only one class |
| Non-member operators taking `D` (e.g. `Ordered<D>`) | a hidden friend is not a member function and has no object parameter to deduce |
| Member types, constructors or destructors of the base that need `D` | none of these are member functions that can have an explicit object parameter ([[dcl.fct#7]]) |
| Dispatching to `D` when called through a base reference or pointer | `Self` can only be deduced as the static type |
| Standard library interfaces that prescribe a CRTP base | `view_interface`, `enable_shared_from_this` and `range_adaptor_closure` all take `D` as a template argument |

Explicit object parameters have one more restriction: such a member function cannot be virtual ([[dcl.fct#7]]), and the templated form can only be defined in headers.

## CRTP and concepts

To require `D` to provide `area_impl`, the most direct approach is a constraint in the base's template head, but that always fails:

```cpp title="constrained-base.cpp" error
#include <concepts>

template<class T>
concept HasAreaImpl = requires(const T& t) {
  { t.area_impl() } -> std::convertible_to<double>;
};

template<HasAreaImpl D>                         // constrain D
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

struct Square : Shape<Square> {                 // error
  double s = 2;
  double area_impl() const { return s * s; }
};
```

The constraint in the template head is checked when `Shape<Square>` is formed, and at that point `Square` is still in its base list with no members at all. Clang 23 reports `constraints not satisfied for class template 'Shape' [with D = Square]`, because `no member named 'area_impl' in 'Square'`.

The constraint has to go somewhere that is checked later. A member function's *requires-clause* is not instantiated with the class ([[temp.inst#19]]) and is checked only when overload resolution considers that function; a `static_assert` in a function body is checked when the body is instantiated.

```cpp run title="crtp-concepts.cpp" ok
#include <concepts>
#include <cstdio>

template<class T>
concept HasAreaImpl = requires(const T& t) {
  { t.area_impl() } -> std::convertible_to<double>;
};

template<class D>
struct Shape {
  double area() const requires HasAreaImpl<D> {   // checked only when area is called
    return static_cast<const D&>(*this).area_impl();
  }
protected:
  Shape() = default;
  ~Shape() {                                       // checked when each D's destructor is defined
    static_assert(HasAreaImpl<D>, "D must provide area_impl()");
  }
};

template<class T>
concept AShape = std::derived_from<T, Shape<T>>;   // T is a CRTP-derived class

void report(const AShape auto& s) { std::printf("%.2f\n", s.area()); }

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

int main() {
  Square sq;
  report(sq);                                      // 4.00
}
```

Add a `struct Blob : Shape<Blob> {};` and create a `Blob` object in `main`, and Clang 23 reports `static assertion failed: D must provide area_impl()`, with notes pointing to the definition of `Blob` and the unsatisfied requirement. Without the `static_assert`, the error appears only when `blob.area()` is called.

A concept like `AShape` can constrain function templates that accept CRTP-derived classes. It is more flexible than a `const Shape<D>&` parameter: `report`'s parameter is the derived class itself, with no conversion to the base. Note that it is not the same as a private constructor plus a friend: the earlier `Circle : Shape<Square>` still fails `AShape<Circle>`, but `Shape<Square>` cannot use a concept to discover from the inside that it has been inherited wrongly.

Going further, if you only need static polymorphism and the base provides no implementation at all, you can drop inheritance and constrain the function template with a concept directly: `void report(const HasAreaImpl auto& s)`. The value of CRTP is that the base can add members to the derived class, which concepts cannot do. The rules for concepts are in [[topics/concepts]].

## When to use it

| Situation | Recommendation |
|---|---|
| The concrete type is known only at run time; heterogeneous containers are needed | virtual functions, `std::variant` or [[patterns/type-erasure]] |
| Base member functions need to call derived members, and C++23 is available | explicit object parameters |
| Each derived class needs its own static data | CRTP |
| Generating non-member functions or operators taking `D` for the derived class | CRTP; for comparison operators prefer defaulted `<=>` and `==` |
| The base's declarations need types from the derived class | CRTP, with `auto` return types, default template arguments or a traits class |
| A set of types only needs to be called uniformly, with no shared implementation | a function template constrained by a concept, no inheritance |
| Several independent pieces of functionality to be combined as needed | see [[patterns/mixin]] and [[patterns/policy-based-design]] |

## Questions

!!! question "1"
    Keep `class Square : Shape<Square>` from the private-base section as private inheritance, and only add `friend Shape;` inside `Square`. Does the program compile?

<details markdown="1">
<summary>Answer</summary>

Yes. The `static_cast` requires the conversion from `Square*` to `Shape<Square>*` to be valid inside `Shape<Square>::area`. By [[class.access.base#4]], a private base is accessible if the conversion occurs in a member or friend of `Square`; `Shape<Square>` is a friend class of `Square`, and its member function bodies may use `Square`'s private members and private bases ([[class.friend#2]]). Clang 23 compiles it, and the program returns 4.

Private inheritance plus a friend lets a CRTP base be a pure implementation detail: outsiders cannot convert a `Square&` to a `Shape<Square>&`, and the interface you want to expose is brought out one name at a time with `using Shape::area;`.
</details>

!!! question "2"
    `struct Tile : Square` redefines `area_impl`. With `Shape<Square>` written using CRTP, and with `Shape` written using an explicit object parameter, whose `area_impl` does `Tile{}.area()` call?

<details markdown="1">
<summary>Answer</summary>

The CRTP version calls `Square::area_impl`. `Tile`'s base is `Square`, and `Square`'s base is fixed as `Shape<Square>`; `static_cast<const Square&>(*this).area_impl()` starts lookup in `Square` and does not see the function of the same name in `Tile`.

The explicit object parameter version calls `Tile::area_impl`. `Self` is deduced from the object expression `Tile{}` as `Tile`, and `self.area_impl()` starts lookup in `Tile`, finding `Tile::area_impl`, which hides `Square::area_impl`. In our tests they return 4 and 5 respectively.

Neither result is overriding in the virtual-function sense: CRTP binds to the `D` written at the point of inheritance, the explicit object parameter binds to the static type at the call site.
</details>

!!! question "3"
    In `crtp-concepts.cpp`, what happens if `main` is changed to `report(Square{});`?

<details markdown="1">
<summary>Answer</summary>

It fails to compile. `Square` has no user-declared constructors and its base is public, so it is an aggregate, and `Square{}` is aggregate initialization ([[dcl.init.aggr]]). The base class subobject `Shape<Square>` is initialized in the context of `main`, which cannot access its `protected` constructor; the temporary is destroyed in `main`, where the `protected` destructor is not accessible either. Clang 23 reports `base class 'Shape<Square>' has protected default constructor` and `temporary of type 'Shape<Square>' has protected destructor`.

`Square sq;` is fine: it calls `Square`'s implicit default constructor, and the base constructor is called from within a member of `Square`, where it is accessible. Once `Square` has a constructor of its own, `Square{}` compiles too.
</details>
