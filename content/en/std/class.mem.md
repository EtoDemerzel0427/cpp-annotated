---
title: Class members
summary: "What can be declared inside the braces of a class definition, why a member function body can see later members, how data members are arranged in an object, and the rules for member functions, static members, bit-fields, class-specific new/delete and nested classes."
updated: 2026-10-19
---

!!! tldr
    - All members of a class are declared once, in the class definition, and none can be added later; apart from forward declarations of nested classes and enumerations, the same member can't be declared twice in the class either.
    - Member function bodies, default arguments, default member initializers and the like are complete-class contexts: there all members of the class are visible and the class is a complete type. A member's type, a return type or an array bound can only see earlier declarations.
    - Later-declared non-static data members have higher addresses (independent of access control since C++23); the address of a standard-layout class object is the address of its first member.
    - An in-class `static const int` with an initializer is only a declaration. When odr-used it needs an out-of-class definition; since C++17 use `static constexpr` or `static inline` instead.
    - Bit-fields have no address and their layout is implementation-defined; class-specific `operator new`/`operator delete` are always static members.

```cpp run ok
struct Widget {
  int id = 0;                    // non-static data member
  static inline int count = 0;   // static data member
  void draw() const;             // member function
  static Widget make();          // static member function
  using Id = int;                // nested type
  struct Part { };               // nested class
  enum Color { red, green };     // nested type; red and green are members too
  template<class T> void set(T); // member template
  unsigned flags : 4;            // bit-field
  friend void swap(Widget&, Widget&);  // friend: not a member
  static_assert(sizeof(int) >= 2);     // declares no member
};
int main() { }
```

What is written inside the braces of a class definition is the **member-specification**. This page first covers its general rules in [class.mem.general]: what a member is, which members are visible where in the class, and how data members are arranged. The second half covers, in turn, member functions, static members, bit-fields, class-specific allocation functions and nested classes. Special member functions are in [[special]], unions in [[class.union]].

## What a member is [class.mem.general]

### Kinds of members (¶3–¶6)

¶3 A class has five kinds of members: data members, member functions ([[class.mfct]]), nested types, enumerators, and member templates ([[temp.mem]]) and their specializations. A specialization of a member template belongs to the corresponding kind: a specialization of a member function template is a member function, a specialization of a member class template is a nested class.

¶5 The kinds of members mean:

- **Data member**: a non-function member introduced by a *member-declarator*, or a member of an anonymous union.
- **Member function**: a member that is a function.
- **Nested type**: a class or enumeration declared in the class, and a type alias declared with `typedef` or `using`. The enumerators of an unscoped enumeration defined in a class are also members of the class.

¶6 Data members and member functions declared `static` are **static members**; the rest are **non-static members**.

¶3 A member first declared in the member-specification of class `X` is a **direct member** of `X` ([[g:direct-member]]); members of anonymous unions count too. Inherited members are not direct members.

### Declarations that declare no member (¶4)

¶4 Several kinds of declarations in a member-specification declare no new member: friend declarations, deduction guides, template declarations whose content is one of those, `static_assert`, `consteval` blocks, *using-declaration*s and empty declarations. A *using-declaration* only brings the name of a base class member into the derived class's scope; it doesn't make it a direct member of the derived class.

Every other member declaration must declare at least one member name or an unnamed bit-field:

```cpp title="member-decls.cpp" error
struct S {
  int;                  // error: declares nothing
  int : 4;              // OK: unnamed bit-field
  static_assert(true);  // OK: declares no member
  ;                     // OK: empty declaration
};
```

By default Clang only gives a `declaration does not declare anything` warning for `int;`; it becomes an error with `-pedantic-errors`. By the standard this program is ill-formed, and a warning satisfies the diagnostic requirement ([[intro.compliance]]).

¶4 ends by defining a word the special member function rules keep using: a direct member or friend declared by a member declaration is **user-declared** ([[g:user-declared]]). A function written with `= default` or `= delete` is also user-declared.

### Members are declared only in the class, and only once (¶3, ¶8, ¶9)

¶3 The member-specification of a class definition declares the complete set of members of the class; none can be added elsewhere. The set of members of a class is fixed once and for all at `}`, so the layout, the virtual function table and the implicitly declared special member functions can all be determined there.

¶8 A member cannot be declared twice in the member-specification, with only two exceptions: a nested class or member class template can be declared and later defined (¶8.1); an enumeration can be introduced with an opaque declaration like `enum E : int;` and later given its full definition (¶8.2). This differs from namespace scope, where functions can be redeclared.

```cpp title="no-redecl.cpp" error
struct S {
  void f();
  void f();            // error: redeclaration
  struct N;
  struct N { };        // OK: ¶8.1
  enum E : int;
  enum E : int { A };  // OK: ¶8.2
};
```

Member functions with the same name are overloads, not redeclarations, as long as their types differ sufficiently ([[basic.scope.scope]]).

¶9 A redeclaration of a member outside the class definition must be a definition, an explicit specialization or an explicit instantiation, and cannot be of a non-static data member:

```cpp title="out-of-class.cpp" error
struct S {
  void f();
  static int s;
  int m;
};
void S::f() { }   // OK: definition
int S::s = 0;     // OK: definition of a static data member
void S::f();      // error: an out-of-class redeclaration must be a definition
int S::m;         // error: a non-static data member cannot be redeclared outside the class
```

## Complete-class contexts (¶10–¶11)

```cpp run title="complete-class-context.cpp" ok
struct S {
  int f() { return g() + sizeof(S); }   // function body
  void h(int x = k) { (void)x; }        // default argument
  void n() noexcept(noexcept(g())) { }  // noexcept-specifier
  int m = g();                          // default member initializer
  int g() const { return 1; }
  static constexpr int k = 42;
};
int main() {
  S s;
  return s.f() == 1 + int(sizeof(S)) ? 0 : 1;
}
```

The body of `f` calls `g`, which is declared later, and takes `sizeof` of `S`, which isn't finished yet. Both are valid because the function body is in a complete-class context of `S`.

¶10 A **complete-class context** ([[g:complete-class-context]]) of a class is one of the following within the member-specification of the class:

- ¶10.1 a function body;
- ¶10.2 a default argument;
- ¶10.3 a default template argument;
- ¶10.4 a *noexcept-specifier*;
- ¶10.5 a function contract specifier (`pre`, `post`) {{c++26}};
- ¶10.6 a default member initializer.

If a nested class is defined within the member-specification of the enclosing class, a complete-class context of the nested class is also a complete-class context of the enclosing class (Note 4).

¶11 A class `C` is complete at a point P in the program if the definition of `C` is reachable from P ([[module.reach]]), or if P is in a complete-class context of `C`.

One way to picture what the compiler does: it processes a class definition in two passes. The first pass handles only the member declarations and builds the full member table; after `}` it goes back to the complete-class contexts. So in a complete-class context, name lookup finds all members of the class, including those declared later ([[basic.scope.class]]), and the class is a complete type.

### Everywhere else only earlier declarations are visible

The declaration parts of members are not complete-class contexts. The type of a data member, a function's return type and parameter types (including a trailing return type), the in-class initializer of a static data member, and the base-clause can only see members declared earlier, and the class is incomplete there:

```cpp title="not-complete-context.cpp" error
struct S {
  auto f() -> decltype(g());   // error: g has not been declared yet
  int g();
  char buf[sizeof(S)];         // error: S is incomplete here
  static constexpr int v = w;  // error: w has not been declared yet
  static constexpr int w = 1;
};
```

These places determine the shape of the class: data member types determine the layout, return and parameter types determine function signatures and thus overloading and virtual function overriding. If they could depend on later declarations, circular dependencies could arise. Function bodies, default arguments and the like don't affect the shape and can safely be deferred until after `}`.

!!! warning "Clang doesn't defer default template arguments"
    Item 10.3 lists the default template arguments of member templates as complete-class contexts. At the time of writing, Clang 23 still reports that `T` has no member `m` for `template<class U = decltype(T::m)> void z(); int m;`, that is, it doesn't defer default template arguments. Code relying on this is currently not portable.

### Default member initializers of nested classes

Deferral creates a problem. A default member initializer of a nested class `B` is also a complete-class context of the enclosing class `A`, so it isn't processed until `A`'s `}`. If code before that point needs to know whether `B` is default-constructible, the answer depends on an initializer that hasn't been parsed yet:

```cpp run title="nested-dmi.cpp"
#include <type_traits>

struct A {
  struct B { int n = 0; };
  // B's default member initializer has not been processed yet
  static constexpr bool v =
      std::is_default_constructible_v<B>;
};

int main() { return A::v; }
```

With Clang 23, `A::v` is `false`. Moreover, the type trait's result is cached, so asking `std::is_default_constructible_v<A::B>` outside the class later also gives `false`.

¶15 says a default member initializer shall not directly or indirectly cause the implicit definition of a defaulted default constructor of the enclosing class, or the exception specification of that constructor; that targets exactly this kind of cycle. But compilers don't agree on indirect cases like type traits: some report an error, others, like Clang, silently give `false`. In practice, don't apply type traits inside the enclosing class definition to a nested class that has default member initializers; move the nested class out of the enclosing class, or give it a user-declared default constructor.

## Default member initializers (¶15)

¶15 A *brace-or-equal-initializer* (an initializer of the form `= expression` or `{ … }`) can only appear in the declaration of a data member. For a non-static data member, it specifies the member's **default member initializer** ([[g:default-member-initializer]]). It is used to initialize the member when a constructor's member initializer list doesn't mention the member ([[class.base.init]]), and in aggregate initialization ([[dcl.init.aggr]]). Initializers of static data members are covered below.

There is no parenthesized form of default member initializer:

<div class="compare" markdown="1">

```cpp error
#include <vector>
struct S {
  std::vector<int> v(10);  // error
};
```

```cpp ok
#include <vector>
struct S {
  std::vector<int> v =
      std::vector<int>(10);  // OK
  std::vector<int> w{1, 2};  // OK
};
```

</div>

Inside a class, the form on the left is parsed as a member function declaration; `10` is not a type, hence the error (Clang: `expected parameter declarator`). Note that the brace form prefers `std::initializer_list` constructors: `w{10}` is a vector with the single element 10.

A default member initializer can use `this` ([[expr.prim.this#5]]) and other members, including members declared later. But members are initialized in declaration order, and reading a member that hasn't been initialized yet is still wrong.

¶15 ends by handling immediate invocations ([[expr.const.imm]]) in a default member initializer, such as calls to `consteval` functions: they are not evaluated, nor checked for being constant expressions, where the initializer appears, but in the constructor that actually uses the initializer. So `std::source_location::current()` in a default member initializer reports the location of the constructor:

```cpp run title="dmi-source-location.cpp" ok
#include <source_location>

struct S {
  std::source_location loc = std::source_location::current();
  S() { }        // line 5
  S(int) { }     // line 6
};

int main() {
  S a, b(1);
  return a.loc.line() == 5 && b.loc.line() == 6 ? 0 : 1;
}
```

## Details of member declaration syntax (¶1–¶2, ¶12–¶19, ¶25–¶26)

The grammar of member declarations is largely the same as for namespace-scope declarations, with a few additions: `override` and `final` (*virt-specifier*), the pure-specifier `= 0`, a trailing *requires-clause* constraining a non-template member function, the bit-field width, and C++26 function contract specifiers. ¶2 says contract specifiers can only appear in a member declaration that declares a function.

### Is `= 0` a pure-specifier or an initializer (¶1, ¶13)

Syntactically, `= 0` can be either a pure-specifier or an initializer. ¶1 and ¶13 distinguish them by the type of the declared entity: if it has function type, `=` introduces a pure-specifier, otherwise an initializer.

```cpp run title="pure-or-init.cpp" ok
struct S {
  using T = void();
  T* p = 0;          // p is a pointer: initializer
  virtual T f = 0;   // f is a function: pure-specifier
};
int main() { }
```

If a member only gets function type through template instantiation, for example `template<class T> struct X { T m = 0; };` instantiated with `T = void()`, the program is ill-formed (Note 1, [[temp.spec.general]]).

### A bit-field width takes the longest expression (¶14)

A bit-field can have a default member initializer (`int x : 8 = 42;`). That raises a question: where does the width expression after `:` end? ¶14 says it takes the longest sequence of tokens that could form a constant expression. The example below is adapted from Example 2 in the standard:

```cpp title="bitfield-parse.cpp" error
int a;
const int b = 0;
struct S {
  int x1 : 8 = 42;               // OK: "= 42" is the initializer
  int x2 : 8 { 42 };             // OK: "{ 42 }" is the initializer
  int y1 : true ? 8 : a = 42;    // OK: all of it is the width
  int y2 : true ? 8 : b = 42;    // error: assignment to const int
  int y3 : (true ? 8 : b) = 42;  // OK: "= 42" is the initializer
  int z : 1 || new int { 0 };    // OK: "{ 0 }" belongs to the new-expression
};
```

The third operand of the conditional operator can be an assignment-expression, so all of `a = 42` goes into the width. The width of `y1` is still a constant expression because evaluation takes the `true` branch and `a = 42` is never executed.

### Friend type declarations (¶12)

A declaration such as `friend class X;` or `friend T;`, where `friend` is followed only by a type, is a *friend-type-declaration*. ¶12 says any member declaration that can syntactically match it is parsed as one. C++26 allows pack expansion, making every type in a template parameter pack a friend at once {{c++26}}:

```cpp run title="variadic-friend.cpp" ok
template<class... Ts>
class Passkey {
  friend Ts...;          // every type in the pack is a friend
  Passkey() = default;
};

struct Alice {
  static Passkey<Alice, struct Bob> key() { return {}; }
};

int main() { (void)Alice::key(); }
```

### Restrictions on specifiers (¶16–¶19)

- ¶16 A member cannot be declared `extern`. A member cannot be declared `thread_local` alone; it must also be `static`: a non-static data member is part of an object, and one copy per thread makes no sense.
- ¶17 Only constructors, destructors and conversion functions can omit the type. C++ has no implicit `int`, so `const x;` is ill-formed. A pure-specifier can only be used on a virtual function.
- ¶18 Attributes at the start of a member declaration appertain to each entity declared by that declaration.
- ¶19 `override` and `final` can each appear at most once, and only on the first declaration of a virtual function; they can't be repeated on an out-of-class definition.

```cpp title="specifiers.cpp" error
struct S {
  extern int e;                // error: ¶16
  thread_local int t;          // error: ¶16, must be static
  static thread_local int ok;  // OK
  const x;                     // error: ¶17, missing type
  void f() = 0;                // error: ¶17, f is not virtual
  virtual void g() override;   // error: g overrides nothing
};
```

### A member can't have the same name as the class (¶25–¶26)

¶25 A static data member, member function, member type, member template, enumerator of an unscoped enumeration member, or member of an anonymous union of class `T` cannot be named `T`. Constructors have no name and are not affected.

The class name `T` is already present in the class scope as the injected-class-name ([[class.pre#2]]), and the constructor declaration syntax `T(...)` depends on it; a member of the same name would conflict. ¶26 forbids a non-static data member named `T` only when the class has a user-declared constructor; this is for C compatibility: in C code, a member with the same name as its struct, as in `struct stat { ... };`, is valid.

```cpp title="same-name.cpp" error
struct T1 { int T1; };          // OK: no user-declared constructor
struct T2 { T2(); int T2; };    // error: ¶26
struct T3 { static int T3; };   // error: ¶25.1
struct T4 { void T4(); };       // error: ¶25.2
```

## Layout of data members in an object (¶7, ¶20, ¶24)

### Member types (¶20)

¶20 A non-static data member cannot have an incomplete type, an abstract class type, or an array of these. So a class `C` cannot contain a member of type `C`, but it can contain a pointer or reference to `C`.

This rule also excludes C99 flexible array members (`struct S { int n; int data[]; };`), because `int[]` is an incomplete type. GCC and Clang accept them as an extension and warn under `-pedantic`.

### One subobject per member; reference members are as big as pointers (¶7)

¶7 An object of class type contains one member subobject for each direct non-static data member.

Whether a reference occupies storage is in general unspecified ([[dcl.ref]]). But for reference members of a class, ¶7 does say something: imagine a class `D` identical to `C` except that each `T&` member is replaced by `T*`; then each member subobject of `C` has the same size, alignment and offset as the corresponding member of `D`, and `C` itself has the same size and alignment as `D`. In other words, a reference member takes as much space as a pointer.

```cpp run title="ref-member-layout.cpp" ok
struct C { int& r; char c; };
struct D { int* r; char c; };
static_assert(sizeof(C) == sizeof(D));
static_assert(alignof(C) == alignof(D));
int main() { }
```

### Later-declared members have higher addresses (¶24)

```cpp run title="member-order.cpp" ok
#include <cstdio>
struct S {
  char a;   // offset 0
  int  b;   // offset 4: 3 bytes of padding after a
  char c;   // offset 8, then tail padding up to 12
public:
  int  d;
private:
  int  e;   // since C++23: always after d
};
int main() {
  S s{};
  bool ordered = (void*)&s.a < (void*)&s.b
              && (void*)&s.b < (void*)&s.c;
  std::printf("sizeof(S) = %zu\n", sizeof(S));
  return ordered ? 0 : 1;
}
```

¶24 Note 8 says that non-variant non-static data members of nonzero size are allocated in declaration order, with later members at higher addresses ([[expr.rel]]). There may be padding between adjacent members for alignment, and bookkeeping for virtual functions and virtual bases (such as the vptr) also takes space. On mainstream 64-bit platforms the example prints `sizeof(S) = 20`.

The two qualifiers mean: an empty member declared with `[[no_unique_address]]` can have zero size, may share an address with other members and doesn't take part in the ordering; members of a union (variant members) are all at the same address.

The compiler won't reorder members for you. Arranging members from largest to smallest alignment to reduce padding is the programmer's job; GCC and Clang's `-Wpadded` reports inserted padding.

!!! history "C++23: no more reordering by access section (P1847)"
    C++20 and earlier only guaranteed increasing addresses in declaration order for members within the same access section (between two access specifiers); the relative order across sections was unspecified. No mainstream compiler ever used that permission. C++23's [[P1847R4]] removed it; the order now depends only on declaration order.

## Common initial sequence and layout compatibility (¶27–¶31)

```cpp run title="tagged-union.cpp" ok
enum Kind { Int, Dbl };
struct IntNode { Kind k; int v; };
struct DblNode { Kind k; double v; };
union Node { IntNode i; DblNode d; };

int value(const Node& n) {
  switch (n.i.k) {   // the tag can be read this way whichever member is active
    case Int: return n.i.v;
    case Dbl: return static_cast<int>(n.d.v);
  }
  return -1;
}

int main() {
  Node n;
  n.d = {Dbl, 2.5};
  return value(n) - 2;
}
```

`n.d` is the active member of the union, yet `value` reads the tag through `n.i.k`. Reading an inactive member of a union is generally undefined behavior; here it is valid thanks to the common initial sequence rule.

### Common initial sequence (¶27)

¶27 The **common initial sequence** ([[g:common-initial-sequence]]) of two standard-layout structs ([[g:standard-layout-struct]], [[class.prop]]) is the longest sequence of non-static data members, compared in pairs in declaration order starting from each one's first non-static data member, such that:

- ¶27.1 corresponding members have layout-compatible types ([[g:layout-compatible-types]]), such as `int` and `const int`;
- ¶27.2 they have the same alignment requirements;
- ¶27.3 if the implementation supports `[[no_unique_address]]`, neither member is declared with it;
- ¶27.4 either both are bit-fields of the same width, or neither is a bit-field.

```cpp run title="cis.cpp" ok
struct A { int a; char b; };
struct B { const int b1; volatile char b2; };  // with A: all members
struct C { int c; unsigned : 0; char b; };     // with A: only the first
struct D { int d; char b : 4; };               // with A: only the first
struct E { unsigned int e; char b; };          // with A: empty
int main() { }
```

The second member of `C` is an unnamed bit-field and the second member of `D` is a bit-field, so the sequence stops there in both. `int` and `unsigned int` are not layout-compatible types, so the common initial sequence of `A` and `E` is empty. Item 27.2 requires the same alignment to exclude the effect of `alignas`: `alignas(8) int` has the same type as `int`, but the offsets of the following members may differ.

### Reading through a union (¶30)

¶30 When the active member of a standard-layout union is of struct type `T1`, you can read a non-static data member `m` of another member of struct type `T2`, provided `m` is in the common initial sequence of `T1` and `T2`. The effect is as if the corresponding member of `T1` were read.

```cpp run title="union-cis.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
  U u = { { 1, 2 } };   // the active member is t1
  return u.t2.c;        // OK: as if reading u.t1.a
  // u.t2.d is not in the common initial sequence; reading it is UB
}

int main() { return f() - 1; }
```

Note 10 reminds you that reading a `volatile` object through a non-`volatile` glvalue is still UB ([[dcl.type.cv]]). The common initial sequence of `A` and `B` includes `volatile char b2`, but reading it through `A::b` is still UB.

### Layout-compatible classes (¶28–¶29)

¶28 Two standard-layout structs whose common initial sequence comprises all members of both are **layout-compatible classes** ([[g:layout-compatible-classes]]). ¶29 Two standard-layout unions are also layout-compatible if they have the same number of non-static data members and corresponding members (in any order) have layout-compatible types. Since C++20 this can be queried with `std::is_layout_compatible`.

### The object and its first member have the same address (¶31)

¶31 If a standard-layout class object has any non-static data members, its address is the same as the address of its first non-static data member (if that member is not a bit-field), and also the same as the address of each of its base class subobjects. So there may be padding in a standard-layout struct, but not at its beginning (Note 11).

Such an object and its first subobject are **pointer-interconvertible** ([[g:pointer-interconvertible]], [[basic.compound#7]]): you can convert between pointers to them with `reinterpret_cast`, and the result points to the other one:

```cpp run title="pointer-interconvertible.cpp" ok
struct Base { int tag; };
struct Wrapper : Base { };                // standard-layout
struct Outer { Base first; int extra; };  // standard-layout

int main() {
  Wrapper w{{1}};
  Outer o{{2}, 3};
  Base* b1 = reinterpret_cast<Base*>(&w);  // equivalent to static_cast
  Base* b2 = reinterpret_cast<Base*>(&o);  // points to o.first
  return b1->tag + b2->tag - 3;
}
```

An array and its first element have the same address but are not pointer-interconvertible ([[basic.compound#7]] Note 7).

## Data member descriptions (¶32) {{c++26}}

¶32 defines, for static reflection, a **data member description** ([[g:data-member-description]]): a sextuple consisting of a type, a name (or none), an alignment (or none specified), a bit-field width (or not a bit-field), whether it is `[[no_unique_address]]`, and a sequence of annotations. Two descriptions are equal if all their components are the same.

`std::meta::data_member_spec` returns a reflection representing a data member description, and `std::meta::define_aggregate` uses these to generate members for an incomplete class ([[meta.reflection.define.aggregate]]). This is C++26's entry point for generating classes in code. At the time of writing, Clang 23 doesn't yet support static reflection, so there is no example here.

## Member functions [class.mfct]

### Member functions defined in the class are inline ([class.mfct] ¶1)

[[class.mfct#1]] A member function attached to the global module is `inline` if it is defined within the class definition ([[dcl.inline]]). A member function declared `inline`, `constexpr` or `consteval` is too, of course.

This rule lets a class definition in a header be included by multiple translation units without violating the ODR ([[basic.def.odr]]). Attachment to the global module is a qualification added in C++20: in a named module (`export module M;`) the class definition is compiled only once, and member functions defined in the class are no longer implicitly inline. That way, changing a function body doesn't force importers to recompile. To make such a function inlinable in a module, write `inline` explicitly.

### Scope of an out-of-class definition ([class.mfct] ¶2)

[[class.mfct#2]] When a member function is defined outside the class, everything after `X::f`, including parameter types, default arguments and the function body, looks up names in the scope of class `X`. The return type is written before `X::f` and is not in class scope, so returning a nested type requires `X::T X::g()`, or a trailing return type `auto X::g() -> T`:

```cpp run title="out-of-class-scope.cpp" ok
struct X {
  typedef int T;
  static T count;
  T g();
  void f(T);
};
X::T X::count = 1;

X::T X::g() { return count; }       // the return type must be qualified
void X::f(T t = count) { (void)t; } // T and count are found in class scope

int main() { X x; x.f(); return x.g() - 1; }
```

### Local classes and declaring member functions with a typedef ([class.mfct] ¶3–¶4)

[[class.mfct#3]] Member functions of a local class (a class defined in a function), if defined, must be defined in the class definition. Functions can't be defined inside functions, so there is nowhere outside the class to define them.

[[class.mfct#4]] A member function can be declared (but not defined) using a typedef for a function type; the resulting type is the same as writing the declarator out. A cv-qualified function type like `typedef void fvc() const;` can be used this way too.

## Non-static member functions [class.mfct.non.static]

[[class.mfct.non.static#1]] A non-static member function can be called for an object of its class or a derived class using class member access syntax (`obj.f()`, `p->f()`). Within a member of the class or a derived class, you can also write just `f()`, which is transformed into `(*this).f()` ([[expr.prim.id]]).

Since C++23 there are two kinds of non-static member functions ([[dcl.fct#8]]):

- **Implicit object member function** ([[g:implicit-object-member-function]]): the traditional form, with the object passed via the implicit `this`;
- **Explicit object member function** ([[g:explicit-object-member-function]]): `this` is written before the first parameter, and the object is passed as an ordinary parameter; commonly called deducing this.

### cv-qualifiers and ref-qualifiers ([class.mfct.non.static] ¶2)

```cpp run title="ref-qualifiers.cpp" ok
#include <string>
#include <utility>

struct Buf {
  std::string s;
  std::string&       get() &       { return s; }
  const std::string& get() const & { return s; }
  std::string        get() &&      { return std::move(s); }
};

Buf make() { return {"hello"}; }

int main() {
  Buf b{"abc"};
  std::string& r = b.get();       // & version
  std::string  v = make().get();  // && version: moves the contents out, no dangling
  return r.size() == 3 && v.size() == 5 ? 0 : 1;
}
```

Note 1 in [[class.mfct.non.static#2]] says an implicit object member function can have a cv-qualifier (which affects the type of `this`) and a ref-qualifier (`&`, `&&`), and both take part in overload resolution.

For overload resolution, an implicit object member function is treated as having an extra first parameter, the **implicit object parameter** ([[g:implicit-object-parameter]], [[over.match.funcs.general#4]]):

| Declaration | Type of the implicit object parameter | Type of `this` |
|---|---|---|
| `void f();` | `X&` (can also bind rvalues, see below) | `X*` |
| `void f() const;` | `const X&` | `const X*` |
| `void f() &;` | `X&` | `X*` |
| `void f() &&;` | `X&&` | `X*` |
| `void f() const &&;` | `const X&&` | `const X*` |

For a member function without a ref-qualifier, the implicit object parameter, although an lvalue reference, can also bind rvalues ([[over.match.funcs.general#5]]), so a temporary can call a non-`const` member function, and `std::string().append("x")` compiles. Ref-qualifiers let you distinguish the two cases, as in the example above.

Overloads with the same name and parameters must either all have ref-qualifiers or none ([[over.load]]):

```cpp title="ref-qual-mix.cpp" error
struct C {
  void f() &;
  void f();   // error: cannot coexist with a ref-qualified overload
};
```

In an implicit object member function with cv-qualifier *cv*, `this` is a prvalue of type pointer to *cv* `X` ([[expr.prim.this#4]]). It can't be assigned to and its address can't be taken. The ref-qualifier doesn't affect the type of `this`; in a `&&` member function, `*this` is still an lvalue. Since C++26, in the predicate of a contract assertion, `const` is additionally added to the type of `this` ([[expr.prim.this#3]]).

[[class.mfct.non.static#3]] An implicit object member function can be virtual ([[class.virtual]]) or pure virtual ([[class.abstract]]).

### Explicit object member functions {{c++23}}

```cpp run title="deducing-this.cpp" ok
#include <string>
#include <utility>

struct S {
  std::string name = "s";

  // one template replaces the four overloads &, const&, &&, const&&
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).name;
  }

  // takes the object by value
  std::size_t len(this S self) { return self.name.size(); }
};

int main() {
  S s;
  const S cs;
  std::string& a = s.get();            // Self = S&
  const std::string& b = cs.get();     // Self = const S&
  std::string c = std::move(s).get();  // Self = S, returns std::string&&
  (void)a; (void)b;
  return c == "s" && cs.len() == 1 ? 0 : 1;
}
```

C++23's [[P0847R7]] allows the object parameter to be written as the first parameter, prefixed with `this` ([[dcl.fct#7]]). Its main uses are:

1. Replacing several overloads on cv- and ref-qualification with one template, like `get` above;
2. Replacing CRTP: `template<class Self> void f(this Self& self)` in a base class gets the actual derived type;
3. Recursive lambdas: `[](this auto self, int n) -> int { return n < 2 ? n : self(n-1) + self(n-2); }`;
4. Taking small objects by value, saving an indirection.

Its restrictions ([[dcl.fct#7]], [[dcl.fct#8]], [[expr.prim.this#4]]):

- The explicit object parameter can only be the first parameter and cannot be a function parameter pack;
- The function can't also have a cv-qualifier or ref-qualifier, and can't be `static` or `virtual`;
- There is no `this` in the function body; members must be accessed as `self.name`;
- A constructor can't have an explicit object parameter ([[class.ctor.general#7]]);
- Taking its address gives an ordinary function pointer, not a pointer to member function: `&S::len` has type `std::size_t(*)(S)`.

```cpp title="deducing-this-errors.cpp" error
struct D {
  void g(this D) const;     // error: cannot be cv-qualified
  static void h(this D);    // error: cannot be static
  virtual void i(this D&);  // error: cannot be virtual
  void j(this D& self) { this->j(); }  // error: cannot use this
};
```

## Static members [class.static]

### Accessing static members ([class.static.general])

[[class.static.general#1]] A static member `s` of class `X` can be referred to as `X::s`, without an object. You can also use class member access syntax `obj.s`; the object expression is then still evaluated, with its side effects:

```cpp run title="static-member-access.cpp" ok
#include <cstdio>

struct process {
  static void reschedule() { }
};

process& g() {
  std::puts("g() called");
  static process p;
  return p;
}

int main() {
  process::reschedule();   // no object needed
  g().reschedule();        // g() is called and prints
}
```

[[class.static.general#2]] Static members obey the usual access rules. `static` can only be written on a member declaration in the class definition, not on an out-of-class definition.

### Static member functions ([class.static.mfct])

[[class.static.mfct#2]] A static member function has no `this`, cannot be `const`- or `volatile`-qualified, and cannot be virtual. The other rules of [[class.mfct]] apply to it as well.

For overload resolution, the implicit object parameter of a static member function matches any object ([[over.match.funcs.general#4]]), so static and non-static `f` can take part in overload resolution together for `obj.f()`. Since C++23, `operator()` and `operator[]` can be static member functions ([[over.call]], [[over.sub]]), and a captureless lambda can be declared `static`, so calls to stateless function objects can skip the `this` argument.

### Static data members ([class.static.data])

[[class.static.data#1]] A static data member is not a subobject of a class object. A static data member that is not `thread_local` has exactly one instance, shared by all objects; a `thread_local` one has one per thread.

[[class.static.data#2]] A static data member cannot be `mutable`, and cannot be a direct member of an unnamed class, a local class, or a class nested within them. These classes have no linkage, so there is no way to define the member outside the class.

```cpp title="static-data-restrictions.cpp" error
void f() {
  struct Local { static int x; };   // error: local class
}
struct { static int y; } anon;      // error: unnamed class
struct M { static mutable int z; }; // error: cannot be mutable
```

[[class.static.data#3]] For a static data member that is not inline, its declaration in the class is not a definition, and its type can be incomplete (other than `void`). The definition goes in namespace scope; its initializer is in the scope of the class and can use other members of the class directly:

```cpp run title="static-data-def.cpp" ok
struct Node;
struct List {
  static Node sentinel;   // Node can be incomplete at the declaration
  static int count;
  static int limit;
};
struct Node { int v; };

Node List::sentinel{0};         // definition: Node must be complete here
int  List::count = 0;
int  List::limit = count + 10;  // count means List::count

int main() { return List::limit - 10; }
```

Once defined, a static data member exists even if no object of the class is ever created. It is initialized and destroyed as described in [[basic.start.static]], [[basic.start.dynamic]] and [[basic.start.term]].

### Which static data members can be initialized in the class ([class.static.data] ¶4)

| Case | In-class initializer | Out-of-class definition |
|---|---|---|
| Non-`volatile`, non-inline `const` integral or enumeration | Allowed; must be a constant expression | Required if odr-used, and must not repeat the initializer |
| `inline` static data member {{c++17}} | Allowed; the in-class declaration is a definition | Not needed |
| `constexpr` static data member | Required (`constexpr` implies `inline`) | Not needed; a redeclaration without an initializer is still allowed but deprecated ([[depr.static.constexpr]]) |
| Others | Not allowed | Required if odr-used |

```cpp run title="static-init-kinds.cpp" ok
#include <string>

struct S {
  static const int N = 3;                // const integral
  static inline std::string name = "S";  // inline: any type
  static constexpr double pi = 3.14159;  // constexpr implies inline
  // static double e = 2.718;            // error: cannot be initialized in the class
  int arr[N];                            // using N's value is not an odr-use
};

int main() {
  S s{};
  return int(sizeof(s.arr) / sizeof(int)) - S::N;
}
```

The first line hides a common trap. `static const int N = 3;` looks like a definition but is only a declaration. If `N` is odr-used ([[g:odr-use]]), for example bound to a reference, having its address taken, or passed to a function like `std::max` that takes `const int&`, a definition must be provided in some translation unit:

```cpp title="odr-use-static-const.cpp" ifndr
struct S { static const int N = 3; };

int main() {
  const int& r = S::N;  // odr-use: bound to a reference
  return r;             // IFNDR: no definition of S::N
}
```

A missing definition violates the ODR and is ill-formed, no diagnostic required (IFNDR). With Clang 23, linking fails at `-O0` (`Undefined symbols ... S::N`), while at `-O2` `r` is constant-folded and linking succeeds.

Since C++17 the fix is to write `static constexpr int N = 3;` or `static inline const int N = 3;`: the in-class declaration of an inline variable ([[g:inline-variable]]) is a definition. Defining class constants in a header no longer requires adding a definition line in some .cpp file; this was one of the main motivations for inline variables in C++17.

[[class.static.data#5]] and [[class.static.data#6]] are two notes: an odr-used static data member has exactly one definition in a valid program (an inline one has an identical definition in every translation unit that uses it); static data members of a class in namespace scope have the same linkage as the class name ([[basic.link]]).

## Bit-fields [class.bit]

### Declaration and basic restrictions ([class.bit] ¶1)

```cpp run title="bitfield-basics.cpp" ok
#include <type_traits>

struct Flags {
  unsigned ready : 1;
  unsigned mode  : 3;
  unsigned       : 4;   // unnamed bit-field: 4 bits of padding
  unsigned count : 8;
};

Flags f{};
static_assert(std::is_same_v<decltype(f.mode), unsigned>);

int main() {
  f.mode = 5;
  f.count = 200;
  return f.mode == 5 && f.count == 200 ? 0 : 1;
}
```

[[class.bit#1]] A member declaration of the form `name : width` declares a **bit-field** ([[g:bit-field]]); the width is an integral constant expression with a value greater than or equal to 0. The rules:

- A bit-field cannot be a static member;
- It must have integral or enumeration type (possibly cv-qualified);
- Being a bit-field is not part of the member's type; in the example above `decltype(f.mode)` is just `unsigned`;
- If the width exceeds the width of the type (for an enumeration, its underlying type), the extra bits are padding bits ([[g:padding-bits]]);
- How bit-fields are allocated and aligned within an object is implementation-defined {{impl}}.

Note 1 says that on some machines bit-fields can straddle allocation units and on others they can't; some assign them right to left, others left to right. So describing a hardware register or network protocol format with bit-fields isn't portable. On little-endian Itanium ABI platforms, bit-fields are allocated starting from the low bits; MSVC has its own rules, particularly about whether adjacent bit-fields of different types share an allocation unit.

### Unnamed and zero-width bit-fields ([class.bit] ¶2)

[[class.bit#2]] A bit-field without a name is an **unnamed bit-field** ([[g:unnamed-bit-field]]), used as padding to conform to externally imposed layouts. It is not a member, cannot be initialized, and cannot be cv-qualified.

An unnamed bit-field of width 0 makes the next bit-field start at a new allocation unit. Only an unnamed bit-field can have width 0.

```cpp run title="zero-width.cpp" impl
#include <cstdio>

struct A { unsigned a : 3; unsigned : 0; unsigned b : 3; };
struct B { unsigned a : 3;               unsigned b : 3; };

int main() {
  // mainstream 64-bit platforms: 8 4
  std::printf("%zu %zu\n", sizeof(A), sizeof(B));
}
```

```cpp title="bitfield-errors.cpp" error
struct C {
  static int s : 3;   // error: cannot be a static member
  const int : 2;      // error: an unnamed bit-field cannot be cv-qualified
  int z : 0;          // error: only an unnamed bit-field can have width 0
  double d : 4;       // error: must have integral or enumeration type
};
```

Zero-width bit-fields are also useful with multiple threads. Adjacent bit-fields of nonzero width belong to the same memory location ([[intro.memory]]), and two threads writing different bit-fields in the same memory location is a data race. Separated by a zero-width bit-field, they become different memory locations and can be modified concurrently.

### Bit-fields have no address ([class.bit] ¶3)

[[class.bit#3]] The `&` operator can't be applied to a bit-field, so there are no pointers to bit-fields, and a non-`const` reference can't bind to one. When a `const T&` is initialized with a bit-field, the reference binds to a temporary holding the bit-field's value; later changes to the bit-field are not visible through the reference:

```cpp run title="bitfield-ref.cpp" ok
struct C { int x : 4; };

int main() {
  C c{3};
  const int& r = c.x;   // binds to a temporary with value 3
  c.x = 1;
  return r == 3 ? 0 : 1;
  // int* p = &c.x;     // error: cannot take the address of a bit-field
  // int& nr = c.x;     // error: a non-const reference cannot bind to a bit-field
}
```

The smallest addressable unit of memory is the byte ([[intro.memory]]). A bit-field starting at bit 5 with width 3 has no address to speak of. This is also why `std::vector<bool>` can only return a proxy object rather than `bool&`.

### Can a stored value be read back unchanged ([class.bit] ¶4)

[[class.bit#4]] specifies when a value reads back unchanged:

- An integral value (other than `bool`): for a bit-field of width N, if the value can be represented by an integer type of width N with the same signedness as the bit-field's type, the value read back is equal;
- A `bool` bit-field (of any width, including 1 bit): storing `true` or `false` reads back the same value;
- An enumeration value stored into an enumeration bit-field of the same type: if the width is large enough to hold all values of the enumeration ([[dcl.enum]]), the value read back is equal. For example, `enum BOOL { FALSE=0, TRUE=1 };` has range 0 to 1, so `BOOL b : 1;` is enough.

When a value that can't be represented is stored, the value of the bit-field is implementation-defined ([[expr.assign]]):

```cpp run title="bitfield-value.cpp" impl
struct C { int x : 4; };  // signed 4 bits: -8 to 7

int main() {
  C c{};
  c.x = 7;    // representable: reads back 7
  c.x = 8;    // not representable: implementation-defined
  return c.x;
}
```

Clang warns on the second assignment with `implicit truncation from 'int' to bit-field changes value from 8 to -8`, and at run time it reads back -8.

Whether an `int` bit-field was signed or unsigned was implementation-defined before C++14; since C++14 it is signed. In C it is still implementation-defined, so in headers shared between C and C++, write `unsigned` explicitly when you need an unsigned bit-field.

## Class-specific operator new and operator delete [class.free]

[[class.free#1]], [[class.free#3]] The allocation functions (`operator new`, `operator new[]`) and deallocation functions (`operator delete`, `operator delete[]`) of a class `T` are static members, even if not declared `static`. When the allocation function is called the object doesn't exist yet, and when the deallocation function is called it has already been destroyed, so there can be no `this`.

[[class.free#2]] Declaring any `operator new` in a class hides all forms of the global `::operator new`, because a *new-expression* looks in class scope first ([[expr.new]]):

```cpp title="class-new-hiding.cpp" error
#include <cstddef>

class Arena;
struct B {
  void* operator new(std::size_t, Arena*);  // placement form only
};
struct D1 : B { };

Arena* ap;
void foo(int i) {
  new (ap) D1;   // B::operator new(std::size_t, Arena*)
  new D1[i];     // ::operator new[](std::size_t): not hidden
  new D1;        // error: ::operator new(std::size_t) is hidden
}
```

### Not virtual, but behaving as if virtual ([class.free] ¶4–¶5)

[[class.free#4]] Allocation and deallocation functions are static, so they can't be virtual. But if the operand of a *delete-expression* points to an object of a class with a virtual destructor, the deallocation function is selected by the destructor of the dynamic type ([[class.dtor#15]]), with the same effect as a virtual function:

```cpp run title="virtual-delete.cpp" ok
#include <cstdio>
#include <new>

struct B {
  virtual ~B() = default;
  void operator delete(void* p, std::size_t) {
    std::puts("B::delete");
    ::operator delete(p);
  }
};
struct D : B {
  int payload[10];
  void operator delete(void* p) {
    std::puts("D::delete");
    ::operator delete(p);
  }
};
struct E : B {
  void log() { std::puts("E::log"); }
  void operator delete(E* p, std::destroying_delete_t) {
    p->log();
    p->~E();
    ::operator delete(p);
  }
};

int main() {
  B* bp = new D;
  delete bp;   // prints D::delete
  bp = new E;
  delete bp;   // prints E::log: handled by E's destroying operator delete
}
```

In the Itanium ABI this is implemented with the deleting destructor (`D0` in the mangled name): `delete bp` calls `D0` virtually, which first destroys the complete object and then calls the `operator delete` selected for its class.

The one in `E` is a C++20 **destroying operator delete** ([[g:destroying-operator-delete]]): its first parameter is a pointer to the class rather than `void*`, and its second parameter is `std::destroying_delete_t`. When a *delete-expression* finds one, it doesn't call the destructor; the function itself is responsible for destroying and freeing. It is useful for classes followed in memory by variable-length data, where the size must be read before freeing.

Note 2 says a virtual destructor has no effect on array `delete[]`. Deleting an array of a derived class through a base class pointer with `delete[]` is undefined behavior ([[expr.delete]]); the element sizes differ, so even the pointer arithmetic is wrong:

```cpp title="array-delete-ub.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra[4]; };

int main() {
  B* bp = new D[3];
  delete[] bp;   // UB: static type differs from dynamic type
}
```

[[class.free#5]] Access checking uses the static type, even when a different deallocation function is actually executed. In `virtual-delete.cpp` above, if `B::operator delete` were `private`, `delete bp;` would be ill-formed, even though `D::operator delete` is what actually runs.

[[class.free#6]] A deallocation function without an explicit *noexcept-specifier* has a non-throwing exception specification.

## Nested classes [class.nest]

[[class.nest#1]] A class declared within another class is a **nested class**. A nested class is a member of the enclosing class, is subject to access control, and can access the enclosing class's private members ([[class.access.nest]]). But objects of the nested class have no connection to objects of the enclosing class; unlike Java's non-static inner classes, they don't implicitly hold an enclosing object. The example below is adapted from Example 1 in the standard:

```cpp title="nested-access.cpp" error
int x;
int y;

struct enclose {
  int x;
  static int s;

  struct inner {
    void f(int i) {
      int a = sizeof(x);  // OK: the operand of sizeof is unevaluated
      x = i;              // error: no enclose object
      s = i;              // OK: enclose::s
      ::x = i;            // OK: global x
      y = i;              // OK: global y
      (void)a;
    }
    void g(enclose* p, int i) {
      p->x = i;           // OK: access through an object
    }
  };
};

inner* p = 0;             // error: must write enclose::inner
```

In `x = i`, name lookup finds `enclose::x` because the nested class's scope is inside the enclosing class. But a non-static member needs an object, and here `this` is an `inner*`, not an `enclose*`, hence the error. `sizeof(x)` is fine because a non-static data member can be named without an object in an unevaluated operand ([[expr.prim.id]]).

[[class.nest#2]] A nested class can be defined in the enclosing class or in the enclosing namespace (`class E::I2 { };`). This enables a form of Pimpl: the header only forward-declares the private nested class, which is defined in the implementation file.

[[class.nest#3]] A friend function defined in a nested class has no special access to members of the enclosing class.

## Implementation notes

!!! impl "Member functions and the ABI"
    - In the Itanium ABI, a non-static member function is just an ordinary function with `this` as its first argument. The mangled name encodes cv- and ref-qualifiers: the `K` in `_ZNK1S3getEv` means `const`, and the ref-qualifiers `&` and `&&` are encoded as `R` and `O`.
    - An explicit object member function is essentially a function taking the object as its first argument; its mangled name differs from an implicit object member function's, and `&S::f` is an ordinary function pointer.
    - A static data member is an ordinary global variable. An `inline` static data member is emitted as COMDAT on ELF and deduplicated by the linker.

!!! impl "Reading and writing bit-fields"
    Writing a bit-field requires a read-modify-write of the whole allocation unit: load, shift, mask, store. That is why the standard treats adjacent bit-fields as one memory location, and concurrent writes to them are a data race. A zero-width bit-field, or a non-bit-field member in between, puts them in separate memory locations, and then the compiler can't generate code that overwrites the adjacent bit-field.

## History

!!! history "History"
    - C++98 only allowed `static const` integral and enumeration members to be initialized in the class. Member functions defined in the class were inline. The signedness of `int` bit-fields was implementation-defined, as in C.
    - C++11 added default member initializers for non-static data members, ref-qualifiers, `constexpr` static data members and `override`/`final`. Nested classes became members of the enclosing class and could therefore access its private members.
    - C++14 made `int` bit-fields signed, and classes with default member initializers could be aggregates.
    - C++17 added inline variables, so `static inline` data members can be defined in the class; `constexpr` static data members became implicitly inline, and out-of-class redeclarations were deprecated.
    - C++20 allowed default member initializers for bit-fields and added `[[no_unique_address]]` and destroying `operator delete`; member functions defined in the class in a named module are no longer implicitly inline.
    - C++23 added explicit object member functions ([[P0847R7]]), stopped reordering member layout by access section ([[P1847R4]]), and allowed `operator()` and `operator[]` to be static.
    - C++26 added `friend Ts...;`, contract specifiers on member declarations, `consteval` blocks and data member descriptions (reflection). The current draft also specifies that reference members have the same layout as pointers ([[class.mem#7]]).

## Common misconceptions

!!! pitfall "Thinking an in-class `static const int` is a definition"
    When it is odr-used (bound to a reference, address taken, passed to a function like `std::max` that takes its argument by reference) it needs an out-of-class definition; otherwise it is IFNDR, typically showing up as a link error only at `-O0`. Since C++17, use `static constexpr` or `static inline` instead.

!!! pitfall "Thinking `*this` is an rvalue in a `&&` member function"
    `*this` is always an lvalue. To pass the object on as an rvalue, write `std::move(*this)`, or use an explicit object parameter `this Self&& self` together with `std::forward<Self>(self)`.

!!! pitfall "Describing hardware registers with bit-fields"
    Bit allocation order, whether bit-fields can straddle allocation units, and alignment are all implementation-defined. Code that must be portable across compilers and architectures should use explicit shifts and masks.

!!! pitfall "Applying type traits to a nested class inside the enclosing class"
    Default member initializers of a nested class aren't processed until the enclosing class is finished; a type trait evaluated before then can be wrong, and the result is cached; see above.

## Questions

!!! question "Question 1"
    Which lines of this class definition have problems?

    ```cpp
    struct S {
      using F = int(int) const;
      F f;                              // (1)
      static constexpr int n = m();     // (2)
      static constexpr int m() { return 1; }
      int g(int x = m()) { return x; }  // (3)
      int arr[m()];                     // (4)
    };
    ```

<details markdown="1">
<summary>Answer</summary>

- (1) OK. Declaring a member function with a `const`-qualified function type alias is equivalent to `int f(int) const;` ([[class.mfct#4]]).
- (2) Error. The in-class initializer of a static data member is not a complete-class context, and `m` hasn't been declared yet here. Even moving `m` earlier doesn't help: `m`'s body is a complete-class context and isn't processed until the class is finished, so when it is used for constant evaluation inside the class it isn't defined yet.
- (3) OK. A default argument is a complete-class context and can use `m`.
- (4) Error. An array bound is not a complete-class context, and as in (2), `m` can't be used for constant evaluation before the class is finished.
</details>

!!! question "Question 2"
    With `struct A { int a; char b; };` and `struct B { int x; char y; short z; };` in a union `u`, and `B` the active member, is reading `u.a.b` valid? What about `u.a.a`? What if `A`'s first member is changed to `alignas(8) int a;`?

<details markdown="1">
<summary>Answer</summary>

The common initial sequence of `A` and `B` is `{a, b}` and `{x, y}`: `int` with `int`, `char` with `char`, layout-compatible types with the same alignment. So both `u.a.a` and `u.a.b` can be read, with the effect of reading `u.b.x` and `u.b.y` ([[class.mem#30]]).

If `A::a` is `alignas(8) int`, the first pair of members has different alignment requirements, violating [[class.mem#27.2]], so the common initial sequence is empty and neither can be read; reading them is UB. `alignas(8)` really does change `A`'s layout, so the condition isn't superfluous.
</details>

!!! question "Question 3"
    Why is access to a class-specific `operator delete` checked using the static type ([[class.free#5]]) rather than the function actually called at run time?

<details markdown="1">
<summary>Answer</summary>

Access control is a compile-time check. At `delete bp;` the compiler only knows that `bp`'s static type is `B*`; it doesn't know the dynamic type at run time and thus doesn't know which deallocation function will be called, so it can only check `B::operator delete`, found via the static type. The `D::operator delete` actually called is called from `D`'s virtual destructor, which is `D` accessing its own member, and that is always accessible. Access to virtual functions works the same way: it is checked using the static type at the call site ([[class.access.virt]]).
</details>

## Summary

| Topic | Rule |
|---|---|
| Set of members | Fixed once by the member-specification; nothing can be added elsewhere; members can't be redeclared (except nested classes and opaque enumerations) |
| Complete-class context | Function bodies, default arguments, default template arguments, `noexcept`, contract specifiers, default member initializers: the whole class is visible and complete |
| Default member initializer | Only `=` or `{}`; `consteval` calls in it are evaluated in the constructor that uses it |
| Layout | Later-declared members have higher addresses, independent of access control since C++23; reference members are laid out like pointers |
| Common initial sequence | The layout-compatible leading part of two standard-layout structs; readable through an inactive union member |
| First member address | A standard-layout class object is pointer-interconvertible with its first non-bit-field member and each base class subobject |
| Member functions | Defined in the class in the global module means inline; cv- and ref-qualifiers determine the implicit object parameter; C++23 allows an explicit object parameter |
| Static members | No `this`; the in-class declaration of a non-inline static data member is not a definition; `inline` and `constexpr` ones can be defined in the class |
| Bit-fields | Integral or enumeration; layout implementation-defined; no address; unnamed bit-fields are not members; a zero-width bit-field starts the next allocation unit |
| Class-specific new/delete | Always static; with a virtual destructor, `delete` selects by dynamic type; access is checked by static type; `delete[]` isn't polymorphic |
| Nested classes | A member of the enclosing class, but objects of the two have no implicit connection |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶21 This paragraph and the next two are notes or examples. This one points out that the restrictions on using non-static members are in [[expr.prim.id]].

¶22 says the type of a non-static member function is an ordinary function type and the type of a non-static data member is an ordinary object type; there are no special member function types or data member types. Pointer-to-member types like `int S::*` are a different matter ([[dcl.mptr]]).

¶23 demonstrates class definition and member access with a binary tree node `tnode`.

[[class.static.mfct#1]] is a note saying the rules of [[class.mfct]] apply to static member functions.

</details>
