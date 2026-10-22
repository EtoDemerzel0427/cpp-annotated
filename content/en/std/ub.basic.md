---
title: Undefined behavior in [basic]
summary: "The 22 kinds of undefined behavior in Annex F.2: implicit object creation, alignment, pointers and glvalues outside lifetime, indeterminate values, the contracts of allocation functions, invalid pointers, unsequenced modifications, data races, forward progress, and the destruction order of static objects; each with its source in the main text, a compilable example and test results on Clang 23."
updated: 2026-10-19
---

!!! tldr
    - A pointer outside an object's lifetime can only be used as a `void*`. Accessing members through it, `delete`, converting to a virtual base, or `dynamic_cast` are all UB, and almost undetectable at run time.
    - Since C++26, reading an uninitialized automatic variable is usually erroneous behavior (with a definite result); only when you explicitly opt out of initialization with `[[indeterminate]]` is the read UB.
    - A pointer after deallocation is not completely untouchable: indirection through it is UB, while comparing it, adding to or subtracting from it, or converting it to `bool` is implementation-defined.
    - `i = i++ + i` is still UB, while `i = i++ + 1` has been defined since C++17; a data race makes the whole program UB.
    - The compiler may assume that a loop doing nothing observable terminates; trivial infinite loops such as `while (true);` are an exception in C++26.

This page is the first part of [[ub]] and corresponds to Annex F.2. The annex files the explicit UB from Clause 6 [basic] and from the execution-model subclauses of Clause 4 ([[intro.object]], [[intro.execution]], [[intro.races]], [[intro.progress]]) all under Clause [basic], and this page keeps its numbering and grouping.

Under each entry's heading come the annex's stable name and the source in the main text. Annex entries are only summaries; judgments must rest on the paragraphs of the main text. The examples have been rewritten so they compile on their own. The test environment is Clang 23.1.3 (arm64 macOS), and run-time detection always uses this command:

```text
clang++ -std=c++2c -O0 -g -fsanitize=address,undefined x.cpp && ./a.out
```

Constant evaluation means putting the same operation into the initializer of a `constexpr` variable and seeing whether the compiler rejects it as [[expr.const.core#2]] requires.

## Object model and alignment

### F.2.1 Implicit object creation has no solution {#intro.object.implicit.create}

`[ub:intro.object.implicit.create]` · main text [[intro.object#13]]

```cpp ub
#include <cstdlib>

void f() {
  void* p = std::malloc(sizeof(int) + sizeof(float));
  *reinterpret_cast<int*>(p) = 0;
  *reinterpret_cast<float*>(p) = 0.0f;   // UB: an int and a float cannot both be alive at the same location
  std::free(p);
}
```

Operations such as `malloc`, `memcpy` and `std::start_lifetime_as` **implicitly create objects** ([[g:implicitly-create-objects]]). The standard does not say which objects are created; it reasons backwards: if there exists a set of objects of implicit-lifetime types that would give the program defined behavior, that set is taken to have been created. If no choice can make the subsequent operations defined, the program has UB.

In the example above, `malloc` creates objects only once. The first write requires an `int` there, the second requires a `float` at the same address, and assignment does not create new objects, so no workable set of objects exists. Switching to a new object explicitly between the two writes, with placement new or `std::start_lifetime_as<float>(p)`, makes the program valid.

In our tests neither ASan nor UBSan reports anything. This kind of UB exists only at the level of the object model and leaves no trace at run time; it shows up only when type-based alias analysis reorders the two writes.

### F.2.2 No suitable created object {#intro.object.implicit.pointer}

`[ub:intro.object.implicit.pointer]` · main text [[intro.object#14]]

```cpp ub
#include <cstdlib>

struct X {
  int a, b;
  ~X() = delete;   // deleted destructor: X is not an implicit-lifetime class
};

X* make_x() {
  X* p = (X*)std::malloc(sizeof(X));   // cannot implicitly create an X
  p->a = 1;                            // UB: no set of objects can make this defined
  return p;
}

struct A { int a; };
struct B { int x; };

B* make_b() {
  A* p1 = (A*)std::malloc(sizeof(A));  // implicitly creates an A (the first use decides the "solution")
  p1->a = 1;
  B* p2 = (B*)p1;
  p2->x = 2;   // UB: p2 points to a live A, and A and B are not similar (see [expr.ref])
  return p2;
}
```

Operations like `malloc` are also specified to return a pointer to a suitable created object. This too works backwards: if no pointer value would give the program defined behavior, it is UB. The annex gives two cases: the type is not an implicit-lifetime type at all, for example because its destructor is deleted; or the pointer is later used as a different, dissimilar type.

In our tests neither snippet gets a sanitizer report. In the second, `A` and `B` have exactly the same layout and nothing looks wrong on the machine, but the standard says it is UB.

### F.2.3 Creating an object in misaligned storage {#basic.align.object.alignment}

`[ub:basic.align.object.alignment]` · main text [[basic.align#1]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct alignas(4) S { int v = 1; };

int main() {
  alignas(S) char s[sizeof(S) + 1];
  S* p = new (s + 1) S();   // UB: s + 1 is 1 byte off 4-byte alignment
  return p->v;
}
```

Every object type has an alignment requirement, and objects must be created at addresses that satisfy it. Placement new knows nothing about the address passed to it and is the easiest place to violate this rule.

UBSan's alignment check reports `constructor call on misaligned address ... which requires 4 byte alignment`. The annex's original example writes `new (&s+1) S()`. `&s + 1` points past the whole array, outside the storage of `s`, which does not match the comment's offset of 1 byte, so it has been changed to `s + 1` here.

## Pointers outside lifetime

[[basic.life#7]] describes a period when storage has been allocated but the object's lifetime has not begun, or the object's lifetime has ended but the storage has not yet been reused or released. During this period, a pointer to the storage may be used as a `void*`, and the following four uses are UB.

### F.2.4 delete of an object outside its lifetime {#lifetime.outside.pointer.delete}

`[ub:lifetime.outside.pointer.delete]` · main text [[basic.life#7.1]]

```cpp ub
struct S {
  float f = 0;
  ~S() {}   // non-trivial
};

void f() {
  S* p = new S;
  p->~S();
  delete p;   // UB: S's lifetime has ended
}
```

Passing such a pointer to a *delete-expression* is UB. The annex's summary applies only to class types with non-trivial destructors, which is the old wording; the current main text ¶7.1 no longer has that restriction, and it is UB whether or not the destructor is trivial.

In our tests neither ASan nor UBSan reports anything: the memory is freed only once and the destructor is empty. As soon as the destructor releases resources, this becomes a double free.

### F.2.5 Accessing members through it {#lifetime.outside.pointer.member}

`[ub:lifetime.outside.pointer.member]` · main text [[basic.life#7.2]]

```cpp ub
struct S { float f = 0; };

float f() {
  S s;
  S* p = &s;
  s.~S();
  return p->f;   // UB: accessing a non-static data member after the lifetime has ended
}
```

Accessing a non-static data member or calling a non-static member function through such a pointer is UB. There is no report at run time; the stack memory of `s` is still there. In constant evaluation Clang rejects it: `read of object outside its lifetime is not allowed in a constant expression`.

### F.2.6 Converting it to a pointer to a virtual base {#lifetime.outside.pointer.virtual}

`[ub:lifetime.outside.pointer.virtual]` · main text [[basic.life#7.3]]

```cpp ub
struct B {};
struct D : virtual B {};

void f() {
  D d;
  D* p = &d;
  d.~D();
  B* b = p;   // UB: converting to a virtual base requires reading the dead object's virtual base offset
}
```

Converting to a non-virtual base just adds an offset known at compile time. Converting to a virtual base requires reading the virtual base offset from the object at run time, and the object is gone. So the former is allowed and the latter is UB. In our tests ASan, UBSan and an explicitly added `-fsanitize=vptr` report nothing.

### F.2.7 Using it as the operand of dynamic_cast {#lifetime.outside.pointer.dynamic.cast}

`[ub:lifetime.outside.pointer.dynamic.cast]` · main text [[basic.life#7.4]]

```cpp ub
struct B { virtual ~B() = default; };
struct D : B {};

void f() {
  D d;
  B* bp = &d;
  d.~D();
  D* dp = dynamic_cast<D*>(bp);   // UB
}
```

`dynamic_cast` has to read the object's dynamic type information. In our tests nothing is reported, and at `-O0` the `dynamic_cast` even returns a non-null pointer: what the object's vtable pointer looks like after destruction depends entirely on the implementation.

## Glvalues outside lifetime

[[basic.life#8]] is the reference version of paragraph 7. A **glvalue** is an expression that refers to an object or function, such as a variable name or a reference. A glvalue referring to an object outside its lifetime can likewise be used only in limited ways.

### F.2.8 Accessing the object through it {#lifetime.outside.glvalue.access}

`[ub:lifetime.outside.glvalue.access]` · main text [[basic.life#8.1]]

```cpp ub
void f() {
  int x = int{10};
  using T = int;
  x.~T();      // pseudo-destructor call: since C++20 it ends x's lifetime
  int y = x;   // UB: reading an object whose lifetime has ended through a glvalue
}
```

Access here means reading or writing the object's value ([[defns.access]]). There is no report at run time, and the value read is still 10; in constant evaluation Clang rejects it, with the same diagnostic as F.2.5.

This example also shows that a **pseudo-destructor call** on a scalar type is not a no-op: it ends the object's lifetime; see [[expr.prim.id.dtor]].

### F.2.9 Calling a member function through it {#lifetime.outside.glvalue.member}

`[ub:lifetime.outside.glvalue.member]` · main text [[basic.life#8.2]]

```cpp ub
struct A {
  void f() {}
};

void g() {
  A a;
  a.~A();
  a.f();   // UB: calling a non-static member function after the lifetime has ended, even though f does nothing
}
```

Even if the member function does nothing, the call itself is UB. In our tests nothing is reported.

### F.2.10 Binding it to a reference to a virtual base {#lifetime.outside.glvalue.virtual}

`[ub:lifetime.outside.glvalue.virtual]` · main text [[basic.life#8.3]]

```cpp ub
struct B {};
struct D : virtual B {};

void f() {
  D d;
  d.~D();
  B& b = d;   // UB
}
```

The reason is the same as in F.2.6: binding a reference to a virtual base requires reading the virtual base offset at run time. In our tests nothing is reported.

### F.2.11 Using it as the operand of dynamic_cast or typeid {#lifetime.outside.glvalue.dynamic.cast}

`[ub:lifetime.outside.glvalue.dynamic.cast]` · main text [[basic.life#8.4]]

```cpp ub
struct B { virtual ~B() = default; };
struct D : virtual B {};

void f() {
  D d;
  B& br = d;
  d.~D();
  D& dr = dynamic_cast<D&>(br);   // UB
}
```

In our tests nothing is reported.

## Reusing an object's storage

### F.2.12 The storage holds a different type at implicit destruction {#original.type.implicit.destructor}

`[ub:original.type.implicit.destructor]` · main text [[basic.life#11]]

```cpp ub
#include <new>

struct T {};
struct B { ~B(); };

void h() {
  B b;
  new (&b) T;   // b's storage is reused by a T, ending b's lifetime
}               // UB: B::~B() is called implicitly here, but the storage holds a T
```

Objects with automatic, static and thread storage duration have their destructors called implicitly at the end of their scope, or at the end of the program or thread. If before that an object of a different type was placed in their storage with placement new, and the original type's destructor is non-trivial, that implicit destruction is UB. The same applies when the scope is left by an exception.

In our tests nothing is reported, and `~B()` runs on that memory as usual. The fix is to put a `B` back with `new (&b) B` before the scope ends.

### F.2.13 Creating an object in the storage of a const complete object {#creating.within.const.complete.obj}

`[ub:creating.within.const.complete.obj]` · main text [[basic.life#12]]

```cpp ub
#include <new>

struct B {
  B();
  ~B();
};

const B b;

void h() {
  b.~B();
  new (const_cast<B*>(&b)) const B;   // UB: recreating an object in the storage of a const complete object
}
```

Creating a new object in the storage that a const complete object with static, thread or automatic storage duration occupies or occupied is UB. The compiler may place such const objects in a read-only segment, or propagate their values as constants. Dynamically allocated const objects are not subject to this entry; for the problem of modifying them see [[ub.dcl#dcl.type.cv.modify.const.obj|F.5.1]].

This example depends on external definitions and was not run. For a related test see F.5.1: writing to `const int g = 3;` through `const_cast`, ASan reports `BUS on unknown address`, because `g` was placed in a read-only page.

## Values and pointers

### F.2.14 Evaluation produces an indeterminate value {#basic.indet.value}

`[ub:basic.indet.value]` · main text [[basic.indet#2]]

```cpp ub
void g() {
  int x [[indeterminate]];
  int y = x;   // UB: an indeterminate value is produced
}

void h() {
  int x;       // C++26: x holds an erroneous value
  int y = x;   // erroneous behavior (EB), not UB
}
```

C++26 splits uninitialized automatic variables into two kinds ([[P2795R5]]). By default, such a variable holds an **erroneous value**, and reading it is erroneous behavior: the result is definite, but the standard considers it an error. When you explicitly opt out of initialization with `[[indeterminate]]`, it holds an **indeterminate value**, and only then is reading it UB. That is the distinction the annex is pointing at when it specifically says an indeterminate value rather than just an erroneous one. `unsigned char` and `std::byte` have a few further exceptions (¶2.1–¶2.3).

Clang 23 does not implement `[[indeterminate]]` yet and warns `unknown attribute 'indeterminate' ignored`; at `-O0` both functions behave the same, reading leftover values from the stack. ASan and UBSan do not check uninitialized reads; that is MSan's job, and MSan does not support macOS. In constant evaluation both are rejected (`read of uninitialized object is not allowed in a constant expression`), because [[expr.const.core#2.8]] excludes both UB and EB.

### F.2.15 An allocation or deallocation function violates its contract {#basic.stc.alloc.dealloc.constraint}

`[ub:basic.stc.alloc.dealloc.constraint]` · main text [[basic.stc.dynamic.general#3]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>
#include <cstdlib>

void* operator new(std::size_t sz) {
  return std::malloc(1);   // UB: the storage returned is smaller than requested
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  long* p = new long(1);   // writes out of bounds already during construction
  delete p;
}
```

A program may replace the global `operator new` and `operator delete`, but the replacements must honor the contracts in [[basic.stc.dynamic.allocation]] and [[basic.stc.dynamic.deallocation]], for example returning, on success, a suitably aligned non-null pointer to at least `size` bytes. If a contract is violated, the whole program has UB, because both the standard library and the compiler rely on these contracts.

ASan reports `heap-buffer-overflow`. It does not understand the contract; the out-of-bounds write simply happens to land in the redzone it set up. The other two violations the annex lists, returning a null pointer for a 0-byte request and `operator delete` throwing, have no dedicated run-time checks.

### F.2.16 Dereferencing the result of a zero-byte allocation {#basic.stc.alloc.zero.dereference}

`[ub:basic.stc.alloc.zero.dereference]` · main text [[basic.stc.dynamic.allocation#2]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

int main() {
  char* c = static_cast<char*>(::operator new(0));
  c[0] = 'X';   // UB
  ::operator delete(c);
}
```

`operator new(0)` must return a non-null pointer distinct from every other allocation, but the pointer cannot be dereferenced: there are no usable bytes there. ASan reports `heap-buffer-overflow`; zero-byte allocations have their redzones too.

### F.2.17 Indirection through an invalid pointer {#basic.compound.invalid.pointer}

`[ub:basic.compound.invalid.pointer]` · main text [[basic.compound#6.1]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int main() {
  int* x = new int{5};
  delete x;
  int y = *x;   // UB: indirection into deallocated storage
  delete x;     // UB: double free
  return y;
}
```

After storage is deallocated, pointer values pointing to it are invalid in all later evaluations ([[g:valid-in-the-context-of]]). Paragraph 6.1 says indirection through an invalid pointer (`*p`, `p->m`) is UB; paragraph 6.2 says converting it to `bool`, using it in addition or subtraction, or comparing it is implementation-defined. People often believe a pointer after deallocation must not be touched at all; that is not accurate.

The annex's summary also lists calling a deallocation function under this entry, which is the old wording; this paragraph of the main text no longer mentions deallocation. The repeated `delete` in the example is still UB, based on the precondition of `operator delete` ([[new.delete.single]]): the pointer passed must not have been invalidated by an earlier deallocation call.

ASan stops at the first one and reports `heap-use-after-free`. In constant evaluation Clang gives `read of heap allocated object that has been deleted` and `delete of pointer that has already been deleted` respectively.

## Execution and concurrency

### F.2.18 Unsequenced side effects {#intro.execution.unsequenced.modification}

`[ub:intro.execution.unsequenced.modification]` · main text [[intro.execution#10]]

```cpp ub
void g(int i) {
  i = 7, i++, i++;   // OK: the comma operator is sequenced; i becomes 9
  i = i++ + 1;       // OK (since C++17): the right operand is sequenced before the assignment
  i = i++ + i;       // UB: the side effect of i++ is unsequenced with the value computation of the right i
  i = i + 1;         // OK
}
```

If a side effect on a memory location is **unsequenced** (no ordering at all is specified between them) relative to another side effect on the same location or a value computation using it, and the two are not potentially concurrent, the behavior is undefined. C++17 added evaluation order for assignment, `<<`, subscripting, function calls and so on, so `i = i++ + 1` is now defined; but the two operands of `+` are still unsequenced.

Under `-Wall` Clang warns `unsequenced modification and access to 'i'` (`-Wunsequenced`); sanitizers do not check this category at run time. Per [[expr.const.core#2.8]], a call to `constexpr int f(int i) { i = i++ + i; return i; }` should not be a constant expression, but Clang 23 only issues the warning above and computes `f(1)` as a constant anyway. This is an omission in the implementation.

### F.2.19 Data races {#intro.races.data}

`[ub:intro.races.data]` · main text [[intro.races#17]]

```cpp ub run flags="-std=c++2c -O1 -g -fsanitize=thread" cc=clang_trunk
#include <thread>
#include <cstdio>

int count = 0;

int main() {
  auto f = [] { for (int i = 0; i < 100000; ++i) count++; };
  std::thread t1{f}, t2{f}, t3{f};   // UB: the three threads' non-atomic read-modify-writes of count race
  t1.join(); t2.join(); t3.join();
  std::printf("%d\n", count);
}
```

When two potentially concurrent actions access the same memory location, at least one is a write, at least one is not atomic, and neither happens before the other, they form a **data race** ([[g:data-race]]), and the whole program has UB. Signal handlers have a special exception.

TSan (`-fsanitize=thread`, which cannot be combined with ASan) reports `WARNING: ThreadSanitizer: data race`, and the program prints a number less than 300000.

### F.2.20 A thread stops making progress {#intro.progress.stops}

`[ub:intro.progress.stops]` · main text [[intro.progress#1]]

```cpp ub
bool stop() { return false; }

void busy() {
  while (!stop());   // UB: no observable progress; the condition is not a constant expression, so this is not a "trivial infinite loop"
}

void spin() {
  while (true);      // OK (C++26): a trivial infinite loop, which cannot be removed
}
```

The implementation may assume that every thread eventually does one of the following: terminate, call `std::this_thread::yield`, call a library I/O function, perform a volatile access, perform an atomic or synchronization operation, or execute a **trivial infinite loop** ([[g:trivial-infinite-loop]], an exception new in C++26, roughly an empty loop whose condition is the constant expression `true`). If a thread neither terminates nor does any of these, the program has UB. This rule lets compilers remove empty loops they cannot prove terminate.

Looking at the assembly with `-O2 -S`, Clang compiles all of `busy` into a single trap instruction `brk #0x1`: it decides that this execution path necessarily leads to UB and generates no loop. `spin` compiles to a `b` instruction that jumps to itself, a genuine infinite loop. That is the practical effect of the trivial infinite loop exception in [[stmt.iter.general]].

## Program termination

### F.2.21 Calling std::exit during destruction of static objects {#basic.start.main.exit.during.destruction}

`[ub:basic.start.main.exit.during.destruction]` · main text [[basic.start.main#4]]

```cpp ub
#include <cstdlib>

struct Exiter {
  ~Exiter() { std::exit(0); }
};

Exiter ex;

int main() {}
// UB: ex is destroyed after main returns, and its destructor calls std::exit again
```

`std::exit` starts destroying objects with static and thread storage duration. If it is called while that destruction is already in progress, it re-enters. In our tests nothing is reported and the program exits with 0; that is just one observation, and the standard guarantees nothing about it.

### F.2.22 Using a destroyed block-scope static variable {#basic.start.term.use.after.destruction}

`[ub:basic.start.term.use.after.destruction]` · main text [[basic.start.term#5]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

struct A {
  int v = 42;
  ~A() { v = -1; std::puts("~A"); }
};
int f() { static A a; return a.v; }

struct B { B() { f(); } };                          // a is first initialized during b's construction
struct C { ~C() { std::printf("f() = %d\n", f()); } };

C c;
B b;   // a finishes construction during b's construction, so it is constructed after c and destroyed before c

int main() {}
// destruction order: b, a, c. ~C calls f(), and control passes through the definition of the destroyed a: UB
```

Static objects are destroyed in the reverse order of the completion of their construction. If, after a block-scope static variable in a function has been destroyed, the destructor of some static object destroyed later calls that function and control passes through the variable's definition, the behavior is undefined. The variable is not reinitialized. Note 2 adds that using the variable indirectly after destruction, through a pointer for example, is also UB.

The program prints `~A` and then `f() = -1`: `a` has already been destroyed, and `f()` reads the value its destructor wrote. Neither ASan nor UBSan reports anything, because the storage of `a` is static and is never freed. This is the well-known static destruction order fiasco.
