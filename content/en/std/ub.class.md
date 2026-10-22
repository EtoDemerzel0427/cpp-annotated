---
title: Undefined behavior in [class]
summary: "The ten kinds of undefined behavior stated explicitly in Clause 11: double destruction, accessing members and bases before construction begins or after destruction ends, pure virtual calls during construction and destruction, calling member functions too early, and virtual calls, typeid and dynamic_cast on other parts of the complete object."
updated: 2026-10-19
---

!!! tldr
    - Once a destructor has been called, the object's lifetime is over; after explicitly calling the destructor of an automatic variable, the implicit destruction at the end of the scope is a second destruction and is undefined behavior.
    - For an object with a non-trivial constructor, its members and bases cannot be accessed before construction begins, not even to take their address or convert to a base pointer; likewise after destruction ends.
    - During construction and destruction, the object behaves like an object of the class the constructor or destructor belongs to. Making a virtual call to a pure virtual function in an abstract class's constructor is undefined behavior.
    - In B's constructor, making a virtual call, `typeid` or `dynamic_cast` through a part of the complete object that is not B's subobject is undefined behavior.
    - Almost none of these are detectable by run-time tools, and compiler warnings cover only the most direct forms.

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.6 subclause corresponds to Clause 11 [class]: ten entries, almost all about the construction and destruction of objects.

Understanding them needs just one model. A class object's lifetime begins when its constructor finishes and ends when its destructor starts ([[basic.life]]). Before and after that, the object is under construction or under destruction, and [[class.cdtor]] says it then behaves like an object of the class whose constructor or destructor is running. Practically every operation that accesses the object bypassing this current type is undefined behavior.

All run results below come from Clang 23 (arm64 macOS), compiled by default with `-O0 -g -fsanitize=address,undefined`; the `vptr` check (the part of UBSan that checks the dynamic type of polymorphic objects) has to be added with `-fsanitize=vptr`.

## Double destruction

### F.6.1 Calling the destructor again on an object whose lifetime has ended {#class.dtor.no.longer.exists}

`[ub:class.dtor.no.longer.exists]` · main text [[class.dtor#18]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct A {
  int* p = new int(1);
  ~A() { delete p; }
};

int main() {
  A a;
  a.~A();
}   // UB: the implicit destruction applies to a, whose lifetime has ended
```

Calling the destructor ends the object's lifetime. After explicitly calling the destructor of an object with automatic storage duration, it is called again implicitly when the scope is left, and that second call acts on an object whose lifetime has already ended. The only remedy is to construct a new object in place with placement new before leaving the scope.

At run time ASan reports `attempting double-free`, with the stack trace pointing to `A::~A()`. In constant evaluation the same operation is rejected with `destroying object 'a' whose lifetime has already ended`.

## Before construction begins and after destruction ends

### F.6.4 Referring to members or bases of an object before its constructor begins {#class.cdtor.before.ctor}

`[ub:class.cdtor.before.ctor]` · main text [[class.cdtor#1]]

If an object has a non-trivial constructor, none of its non-static members or base class subobjects may be referred to before the constructor begins executing. If all its constructors are trivial, there is no such restriction. The main text uses global objects to show how this affects initialization order:

```cpp ub
struct X { int i; };
struct Y : X { Y(); };                  // non-trivial
struct A { int a; };
struct B : public A { int j; Y y; };    // non-trivial (because of member y)

extern B bobj;
B* pb = &bobj;                          // OK: address of the whole object
int* p1 = &bobj.a;                      // UB: refers to a base class member
int* p2 = &bobj.y.i;                    // UB: refers to a member of a member
A* pa = &bobj;                          // UB: conversion to a base class pointer
B bobj;                                 // definition of bobj (dynamic initialization)

extern X xobj;
int* p3 = &xobj.i;                      // OK: X's constructors are all trivial
X xobj;
```

`pb`, `p1`, `p2` and `pa` are all initialized before the dynamic initialization of `bobj`. Taking the address of the whole object is fine, but taking the address of a member or converting to a base class pointer refers to a subobject, and at that point construction of `bobj` has not begun.

The annex picks a different example: in a member initializer, taking the address of a member of a member that has not yet been constructed and has a virtual base.

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct W { int j; };
struct X : virtual W {};
struct Y {
  int* p;
  X x;
  Y() : p(&x.j) {}   // UB: x has not been constructed yet
};

int main() { Y y; }
```

At run time the `vptr` check reports `cast to virtual base of address … which does not point to an object of type 'X'`. To find `j` in the virtual base `W`, the virtual base offset recorded in `x` has to be read, and since `x` has not been constructed, that information has not been written yet.

### F.6.7 Forming a pointer to a direct member before construction begins or after destruction completes {#class.cdtor.form.pointer}

`[ub:class.cdtor.form.pointer]` · main text [[class.cdtor#3]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { int i = 0; };
struct B {
  int* p;
  A a;
  B() : p(&a.i) {}   // UB: construction of a has not begun when p is initialized
};

int main() { B b; std::printf("%d\n", *b.p); }
```

To form a pointer to a direct non-static member of an object `obj`, or to access that member's value, construction of `obj` must have begun and its destruction must not have completed. Members are initialized in declaration order, so when `p` is initialized, construction of `a` has not begun.

At compile time Clang warns `field 'a' is uninitialized when used here [-Wuninitialized]`; running it reports nothing and prints `0`. Without virtual bases, `&a.i` is just a fixed offset and nothing is wrong at the hardware level, which is why this undefined behavior is hard to notice. Declaring `p` after `a` removes the problem.

### F.6.6 Converting to a base class pointer before construction or after destruction {#class.cdtor.convert.pointer}

`[ub:class.cdtor.convert.pointer]` · main text [[class.cdtor#3]]

When converting a pointer to X into a pointer to its base class B, construction must have begun and destruction must not have completed for X itself and for all of X's bases that derive from B. Virtual bases give more than one path to B, which the annex illustrates with this example:

```cpp ub
struct A { };
struct B : virtual A { };
struct C : B { };
struct D : virtual A { D(A*); };
struct X { X(A*); };

struct E : C, D, X {
  E() : D(this),   // UB: E* → A* may go through E* → D* → A*, and D is not yet constructed
                   // writing D((C*)this) is valid: E() has begun and C is fully constructed
        X(this) {} // OK: when X is constructed, C, B, D and A are all fully constructed
};
```

Adding code to the constructors of `D` and `X` that reads a member of the object `p` points to and running it on Clang 23, both print normally with no report. Clang computes `A*` through the virtual base offset recorded by `E` itself, which happens not to go through `D`. But the standard does not specify which path the conversion takes, so this is still undefined behavior.

### F.6.5 Referring to members or bases of an object after its destructor has finished {#class.cdtor.after.dtor}

`[ub:class.cdtor.after.dtor]` · main text [[class.cdtor#1]]

This is the mirror image of F.6.4: for an object with a non-trivial destructor, its members and bases likewise cannot be referred to after destruction completes.

```cpp ub
struct X {
  int i;
  ~X();   // non-trivial
};

X& g() {
  static X x;
  return x;
}

void f() {
  X* px = &g();
  px->~X();
  int j = px->i;   // UB: accessing a member after destruction completes
}
```

`x` has static storage duration and its memory still exists after destruction, so running this kind of code reports nothing on Clang 23. When this program exits, `x` is destroyed once more, which is the undefined behavior of F.6.1.

## Virtual calls and type queries during construction and destruction

### F.6.2 Making a virtual call to a pure virtual function in an abstract class's constructor or destructor {#class.abstract.pure.virtual}

`[ub:class.abstract.pure.virtual]` · main text [[class.abstract#6]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
struct B;
void call(B*);

struct B {
  virtual void f() = 0;
  B() { call(this); }   // indirectly makes a virtual call to a pure virtual function
};
void call(B* b) { b->f(); }   // UB: *b behaves as a B object here, and B::f is pure virtual

struct D : B { void f() override {} };

int main() { D d; }
```

While the `B` part of a `D` is being constructed, the object behaves as a `B` object ([[class.cdtor#4]]), and the virtual call `f()` selects the final overrider in `B`, which is the pure virtual `B::f`. Direct and indirect calls both count: calling an ordinary function from the constructor, which then makes a virtual call to the pure virtual function, is also undefined behavior.

When the constructor directly writes `f();`, Clang 23 warns `call to pure virtual member function 'f' has undefined behavior; overrides of 'f' in subclasses are not available in the constructor of 'B' [-Wcall-to-pure-virtual-from-ctor-dtor]`. The indirect call above gets no warning. At run time both forms land on the pure virtual placeholder entry in B's vtable, and libc++abi prints `Pure virtual function called!` and aborts the program.

### F.6.3 Calling a member function before all bases are initialized {#class.base.init.mem.fun}

`[ub:class.base.init.mem.fun]` · main text [[class.base.init#18]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { A(int v) { std::printf("%d\n", v); } };

struct B : A {
  int j = 7;
  int f() { return j; }
  B() : A(f()) {}   // UB: a member function is called before base A is initialized
};

int main() { B b; }
```

Member functions can be called during construction and destruction, and `typeid` and `dynamic_cast` can be applied to the object. But doing these things at the following three times is undefined behavior:

- in a constructor's member initializer list (including in functions it calls directly or indirectly), before the initialization of all bases has completed;
- in a precondition assertion of a constructor;
- in a postcondition assertion of a destructor (for the last two, see [[dcl.contract.func]], C++26 contracts).

Once all bases have been initialized, calling member functions while initializing members is valid, though members not yet initialized still cannot be read. The annex's example also shows multiple inheritance: in `D() : C(f()), i(f())`, the first call is undefined behavior because base `C` has not been initialized yet; the second call is valid.

Running it gives no sanitizer report and prints a garbage value, because `j` has not been initialized yet at that point.

### F.6.8 Making a virtual call through another part of the object during construction or destruction {#class.cdtor.virtual.not.x}

`[ub:class.cdtor.virtual.not.x]` · main text [[class.cdtor#4]]

Let x be the object under construction; it may be a base class subobject of some complete object. In x's constructor, a virtual call made through x itself or one of x's base class subobjects selects the final overrider in the constructor's class. If a virtual call is applied, through explicit member access, to a part of the complete object other than x, such as another base class subobject of the complete object, the behavior is undefined.

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct V {
  virtual void f() { std::puts("V::f"); }
  virtual void g() { std::puts("V::g"); }
  virtual ~V() = default;
};
struct A : virtual V { void f() override { std::puts("A::f"); } };
struct B : virtual V {
  void g() override { std::puts("B::g"); }
  B(V* v, A* a) {
    f();      // V::f, not A::f
    g();      // B::g, not D::g
    v->g();   // OK: v points to B's base V, calls B::g
    a->f();   // UB: A is not a base of B
  }
};
struct D : A, B {
  void f() override { std::puts("D::f"); }
  void g() override { std::puts("D::g"); }
  D() : B((A*)this, this) {}
};

int main() { D d; }
```

`D` constructs base `A` first, then `B`. In `B`'s constructor, `a` points to the `A` subobject of the complete object, which is not part of the `B` under construction.

On Clang 23 this prints `V::f`, `B::g`, `B::g`, `V::f` in turn. The undefined call `a->f()` calls neither `A::f` nor `D::f` but `V::f`: at this point the vptr (the hidden pointer to the virtual function table) of the A subobject points to some temporary vtable used during the construction of `D`.

### F.6.9 Using typeid on another part during construction or destruction {#class.cdtor.typeid}

`[ub:class.cdtor.typeid]` · main text [[class.cdtor#5]]

During construction or destruction, if the operand of `typeid` refers to the object under construction, the result is the `type_info` of the constructor's class. This requires the static type of the operand to be that class or one of its bases; otherwise the behavior is undefined.

```cpp ub
#include <typeinfo>

struct V { virtual void f(); };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A* a) {
  typeid(*this);   // type_info of B
  typeid(*v);      // OK: V is a base of B, gives B's type_info
  typeid(*a);      // UB: A is not a base of B
}
```

Printing the `name()` of these three `typeid`s on Clang 23 gives `1B` for all of them: the undefined one also claims the A subobject's type is B.

### F.6.10 Using dynamic_cast on another part during construction or destruction {#class.cdtor.dynamic.cast}

`[ub:class.cdtor.dynamic.cast]` · main text [[class.cdtor#6]]

```cpp ub
struct V { virtual void f(); };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A* a) {
  dynamic_cast<B*>(v);   // OK: V is a base of B, the result is a B*
  dynamic_cast<B*>(a);   // UB: A is not a base of B
}
```

During construction or destruction, `dynamic_cast` treats the object under construction as a most derived object whose type is the constructor's class. If the static type of the operand is not that class or one of its bases, the behavior is undefined.

On Clang 23, `dynamic_cast<B*>(a)` returns a null pointer. For the three examples of F.6.8 to F.6.10, ASan, UBSan and the `vptr` check report nothing.
