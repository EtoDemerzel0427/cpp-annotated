---
title: Exam 1 · Object model and lifetime
summary: 25 questions on where objects come from, when lifetime begins and ends, whether old names still work after storage is reused, how long temporaries live, and through which glvalue types an object may be read or written. Every question comes with a verdict and paragraph references into the current draft.
tags: object model, lifetime, storage duration, temporaries, launder, unions, aliasing, UB
updated: 2026-10-20
---

!!! tldr
    - Scope: object creation and implicit object creation, storage duration and addresses, the beginning and end of lifetime, storage reuse, transparent replacement and `std::launder`, temporaries and lifetime extension, the active member of a union, trivially copyable types, the type-accessibility rule, and invalid pointer values.
    - 25 questions: 15 verdict, 7 multiple choice, 3 open-ended, roughly increasing in difficulty. Suggested time: 90 minutes.
    - For verdict questions, answer with the most severe property of the whole program: `ok` well-formed with defined behavior, `error` ill-formed, `ub` undefined behavior, `impl` implementation-defined. All code is judged against the current working draft, `-std=c++2c` by default.
    - Each explanation gives the answer first, then the chain of reasoning with `[clause]/paragraph` references, and finally why the plausible-looking alternatives are wrong.

## 1. Where objects come from

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program. `Record` has a `std::string` member, yet its storage comes from `std::malloc` and no constructor is called.

```cpp run
#include <cstdlib>
#include <string>

struct Record {
    int id;
    std::string name;
};

int main() {
    auto* p = static_cast<Record*>(std::malloc(sizeof(Record)));
    if (!p) return 1;
    p->id = 42;
    int r = p->id;
    std::free(p);
    return r == 42 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed, with defined behavior (ok).**

1. `std::malloc` implicitly creates objects in the storage it returns and returns a pointer to a suitable created object ([[c.malloc#4]]). Implicit creation only creates objects of implicit-lifetime types, and only when doing so gives the program defined behavior ([[intro.object#13]], [[intro.object#14]]).
2. `Record` is an aggregate whose destructor is not user-provided, so it is an implicit-lifetime class ([[class.prop#8]], item 8.1). The member `std::string` is not an implicit-lifetime type, but that does not affect the classification of the enclosing class.
3. So `malloc` can create a `Record` object together with its `int` subobject `id`. The returned pointer points to that `Record`, and both the write and the read of `p->id` are defined. Per note 4 of [[intro.object#13]], the lifetime of the `name` subobject has not begun, but the program never touches it.
4. `std::free` releases the storage, ending the lifetime of the `Record` without calling its destructor, which [[basic.life#6]] permits.

Many people assume that a member with a non-trivial constructor forces you to use `new`. Two things have to be kept apart: whether the enclosing object can be implicitly created (it can), and which subobjects thereby begin their lifetime (only those of implicit-lifetime type). Change one thing, use `name`, and the behavior is undefined:

```cpp run ub
#include <cstdlib>
#include <string>

struct Record {
    int id;
    std::string name;
};

int main() {
    auto* p = static_cast<Record*>(std::malloc(sizeof(Record)));
    if (!p) return 1;
    p->name = "x";   // UB: p->name is not within its lifetime
    std::free(p);
}
```

`p->name` is a glvalue referring to an object outside its lifetime; calling the member function `operator=` through it is undefined behavior listed in [[basic.life#8]], item 8.2. In our tests the program crashes inside `operator=` after reading a garbage pointer. Another way to break it is to give `Record` a `~Record() {}`: the destructor becomes user-provided, so item 8.1 no longer holds; the class has no trivial eligible constructor either, so item 8.2 does not hold. `Record` is no longer an implicit-lifetime class, and even `p->id = 42` becomes undefined behavior. See [[papers/implicit-object-creation]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Which of the following objects does not have dynamic storage duration?

- A. `*p` in `alignas(int) unsigned char buf[4]; int* p = ::new (buf) int(1);`, where `buf` is a block-scope local variable
- B. An object implicitly created in storage returned by `std::malloc`
- C. A non-static data member subobject of a `Node` object created by `new Node`
- D. The parameter `s` when a function `void f(std::string s)` is called

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

Storage duration is a property of an object, determined by the construct that creates it ([[basic.stc.general#1]]), not by which region of memory it happens to live in.

- A has dynamic storage duration. [[expr.new#10]] says every object created by a new-expression has dynamic storage duration, and placement new is no exception, even when the storage comes from a local array. The storage of this `int` is still the storage of `buf`: when the block exits, `buf`'s storage is released and the lifetime of `*p` ends with it ([[basic.life#2]], item 2.5).
- B has dynamic storage duration: implicitly created objects are classified with objects created by new-expressions ([[basic.stc.general#2]]).
- C has dynamic storage duration: a subobject has the storage duration of its complete object ([[basic.stc.general#4]]).
- D has automatic storage duration: variables that belong to a parameter scope have automatic storage duration ([[basic.stc.auto#1]]).

A is the easiest one to get wrong. Dynamic storage duration does not mean "on the heap"; it only says the object is not implicitly destroyed at the end of some scope.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

What does the following program print?

```cpp run
#include <cstdio>

struct E {};
struct F {};

struct S {
    [[no_unique_address]] E a;
    [[no_unique_address]] E b;
};

struct T {
    [[no_unique_address]] E a;
    [[no_unique_address]] F b;
};

int main() {
    S s;
    T t;
    std::printf("%d %d\n",
                static_cast<void*>(&s.a) == static_cast<void*>(&s.b),
                static_cast<void*>(&t.a) == static_cast<void*>(&t.b));
}
```

- A. Always `0 0`
- B. Always `0 1`
- C. The first number is always 0; the second may be 0 or 1
- D. Either number may be 0 or 1

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

1. A member declared `[[no_unique_address]]` is a potentially-overlapping subobject ([[dcl.attr.nouniqueaddr#1]], [[intro.object#7]]). If such a member is of a class type with no subobjects, the standard does not require it to have nonzero size; it is not a base class subobject, so whether it has zero size is implementation-defined ([[intro.object#8]]).
2. Two objects with overlapping lifetimes may share an address only in the four cases listed in [[intro.object#10]]; otherwise their addresses must differ. `s.a` and `s.b` are not nested within each other and are not potentially non-unique objects such as string literals; item 10.3 requires their types not to be similar, but both are `E`. So `&s.a != &s.b` always holds and the first number is always 0.
3. The types of `t.a` and `t.b`, `E` and `F`, are not similar. As long as one of them has zero size, item 10.3 lets them share an address. Whether either has zero size is implementation-defined; the address of a zero-size subobject is some unspecified byte occupied by its complete object (last sentence of [[intro.object#10]]).

Clang 23 (Itanium ABI) prints `0 1`. MSVC ignores the standard `[[no_unique_address]]` (it offers `[[msvc::no_unique_address]]` instead) and prints `0 0`, which also conforms. So B is wrong: it takes one implementation's behavior for a guarantee.

That two objects of the same type must have distinct addresses is the foundation of object identity: comparing two `E*` with `==` must be able to tell two different `E` objects apart.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program.

```cpp run
int main() {
    alignas(int) unsigned char buf[sizeof(int)];
    int* p = reinterpret_cast<int*>(buf);
    *p = 5;
    return *p == 5 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. When the lifetime of `buf` begins, objects are implicitly created in the storage it occupies ([[intro.object#16]]), so there can be an `int` object in `buf`. The question is not whether the object exists but which object `p` points to.
2. `reinterpret_cast<int*>(buf)` is equivalent to converting to `void*` and then `static_cast`ing to `int*` ([[expr.reinterpret.cast#7]]). By [[expr.static.cast#12]], the result points to an `int` object only if the object the original pointer points to is pointer-interconvertible with it; otherwise the pointer value is unchanged.
3. `buf` decays to a pointer to `buf[0]`. `buf[0]` and an `int` nested within `buf` satisfy none of the cases in [[basic.compound#7]] (same object, union and member, standard-layout class and its first member or base), so `p` still points to the `unsigned char` object `buf[0]`.
4. `*p` refers to `buf[0]` ([[expr.unary.op#1]]). Modifying an `unsigned char` object through a glvalue of type `int` violates [[basic.lval#11]], and the behavior is undefined. No choice of implicitly created objects can change the pointer value of `p`, so [[intro.object#13]] cannot rescue it.

One change makes it defined:

```cpp run ok
#include <new>

int main() {
    alignas(int) unsigned char buf[sizeof(int)];
    int* p = std::launder(reinterpret_cast<int*>(buf));
    *p = 5;                     // OK
    return *p == 5 ? 0 : 1;
}
```

The precondition of `std::launder` requires an object of similar type within its lifetime at that address ([[ptr.launder#2]]). Implicit object creation can supply exactly that `int`, so `launder` returns a pointer to it.

The `malloc` in question 1 needs no `launder` because `malloc` returns a pointer to a created object ([[intro.object#14]]), whereas the beginning of an array's lifetime yields no such return value. Clang gives no diagnostic for the original program and the result matches intuition. [[P3006R1]] (Launder less) proposes dropping the need for `launder` in this situation; the current draft has not adopted it.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program. The element type of `raw` is `char`.

```cpp run
#include <new>
#include <string>

struct Slot {
    std::string label;
    alignas(int) char raw[sizeof(int)];
};

int main() {
    Slot s;
    ::new (s.raw) int(42);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. Only arrays of `unsigned char` and of `std::byte` can provide storage for other objects ([[intro.object#3]]); an array of `char` cannot.
2. The new `int` is not a subobject of `s` either: to be one it would have to be of the same type as `raw` and exactly overlay it ([[intro.object#2]]). So it is not nested within `s` ([[intro.object#4]]).
3. The storage of `s` is reused by an object not nested within `s`, so the lifetime of `s` ends ([[basic.life#2]], item 2.5).
4. At the end of `main`, the destructor of `s` is implicitly called ([[class.dtor#14]]). `Slot`'s destructor is non-trivial, but there is no `Slot` object at that location, which is undefined behavior per [[basic.life#11]]; invoking a destructor on an object whose lifetime has ended also violates [[class.dtor#18]].

Changing only the element type gives a well-formed program with defined behavior:

```cpp run ok
#include <new>
#include <string>

struct Slot {
    std::string label;
    alignas(int) unsigned char raw[sizeof(int)];
};

int main() {
    Slot s;
    ::new (s.raw) int(42);   // OK: raw provides storage for the int, which is nested within s
}
```

Now `raw` provides storage for the `int`, so the `int` is nested within `raw` and hence within `s` ([[intro.object#4]], items 4.2 and 4.3). Neither `s` nor `raw` ends its lifetime. The two versions behave identically at run time and the sanitizers report nothing; the difference exists only in the standard's object model. This is why buffers meant to hold other objects should be declared as arrays of `unsigned char` or `std::byte`.

</details>
</div>

## 2. End of lifetime and storage reuse

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program. The destructor of the first string is never called.

```cpp run
#include <new>
#include <string>

int main() {
    auto* p = new std::string(100, 'x');
    ::new (p) std::string("y");
    bool ok = (*p == "y");
    delete p;
    return ok ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed, with defined behavior (ok). The program leaks 100 bytes, but a leak is not undefined behavior.**

1. Placement new reuses the storage of the first string, which ends its lifetime ([[basic.life#2]], item 2.5). [[basic.life#6]] explicitly allows ending the lifetime of a class object this way without calling its destructor, and says the destructor is then not implicitly called. Note 4 in the same paragraph warns that correct programs often depend on the destructor being called, but notes are not normative.
2. The original object is transparently replaceable by the new one ([[basic.life#9]], item 9.1): both are complete objects, the original is not `const`, the storage exactly overlays, and the types are the same. So `p` automatically points to the new object ([[basic.life#10]]), and both `*p == "y"` and `delete p` operate on the new object.
3. The heap buffer of the first string is never released. That is a resource leak, which the standard does not treat as undefined behavior.

If the original object is `const`, transparent replacement does not apply:

```cpp run ub
#include <new>
#include <string>

int main() {
    const auto* p = new const std::string(100, 'x');
    ::new (const_cast<std::string*>(p)) const std::string("y");
    delete p;   // UB: p still points to the original object, whose lifetime has ended
}
```

Item 9.1.1 requires the original object not to be `const`, so `p` does not automatically point to the new object. `p` points to an object whose lifetime has ended, and using it as the operand of a delete-expression is undefined behavior per [[basic.life#7]], item 7.1. Writing `delete std::launder(p)` makes it defined.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program.

```cpp run
#include <new>

struct S { int m; };

int main() {
    S x{1};
    ::new (&x) S{x.m + 1};
    return x.m;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. The last sentence of [[basic.life#2]] says that when a new-expression is evaluated, the storage is considered reused after the allocation function returns and before the new-initializer is evaluated. Here the allocation function is `operator new(std::size_t, void*)`.
2. So when `x.m + 1` is evaluated, the lifetime of the original `x` has already ended and the lifetime of the new object has not yet begun.
3. `x` is transparently replaceable by the new object, but [[basic.life#10]] says the name can be used to manipulate the new object only once its lifetime has begun. At this point `x.m` refers to the original object outside its lifetime, and reading its value is undefined behavior per [[basic.life#8]], item 8.1. This is exactly the situation of example 1 in [[basic.life#2]].

In our tests the program returns 2 with no diagnostic. Reading the value first avoids the problem:

```cpp run ok
#include <new>

struct S { int m; };

int main() {
    S x{1};
    int old = x.m;           // read the old value first
    ::new (&x) S{old + 1};   // OK
    return x.m;              // OK: x refers to the new object, value 2
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program. `reset` tries to assign a new value to an `Entry` by destroying it and then constructing in place, and this time `load` throws.

```cpp run
#include <new>
#include <stdexcept>
#include <string>

struct Entry { std::string text; };

std::string load(bool fail) {
    if (fail) throw std::runtime_error("load failed");
    return std::string(64, 'n');
}

void reset(Entry& e, bool fail) {
    e.~Entry();
    ::new (&e) Entry{load(fail)};
}

int main() {
    try {
        Entry e{std::string(64, 'o')};
        reset(e, true);
    } catch (const std::exception&) {
    }
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. `e.~Entry()` ends the lifetime of `e` ([[class.dtor#18]]).
2. The initializer of the placement new throws, so the new `Entry` is never constructed and there is no `Entry` object at `e`'s location.
3. The exception leaves the `try` block. `e` has automatic storage duration and `Entry`'s destructor is non-trivial, so the destructor is implicitly called when the block exits ([[class.dtor#14]]). [[basic.life#11]] requires an object of the original type to occupy that location at this point, otherwise the behavior is undefined, and says explicitly that this holds even if the block is exited with an exception.
4. It is also a second destructor call on an object whose lifetime has ended ([[class.dtor#18]]).

In our tests ASan reports `attempting double-free`: the buffer of the first string is freed once by `e.~Entry()` and again by the destructor run during stack unwinding.

The fix is to finish everything that can throw before touching `e`:

```cpp run ok
#include <stdexcept>
#include <string>

struct Entry { std::string text; };

std::string load(bool fail) {
    if (fail) throw std::runtime_error("load failed");
    return std::string(64, 'n');
}

void reset(Entry& e, bool fail) {
    e = Entry{load(fail)};   // construct the new value first; if it throws, e is left unchanged
}

int main() {
    try {
        Entry e{std::string(64, 'o')};
        reset(e, true);
    } catch (const std::exception&) {
    }
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Of the four lettered lines below, which one has undefined behavior? (Exactly one does.)

```cpp run
struct Counter {
    mutable int hits;
    int limit;
    Counter() : hits(0), limit(0) { limit = 10; }
};

const Counter cfg;

int main() {
    const_cast<Counter&>(cfg).hits = 1;      // A
    int* p = const_cast<int*>(&cfg.limit);   // B
    int n = 0;
    const int& r = n;
    const_cast<int&>(r) = 2;                 // C
    *p = 3;                                  // D
}
```

- A. Line A
- B. Line B
- C. Line C
- D. Line D

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

The rule is in [[dcl.type.cv#4]]: modifying a const object during its lifetime is undefined behavior. The key is which objects are const objects. By [[basic.type.qualifier#1]], item 1.1, a const object is an object of type `const T` or a non-`mutable` subobject of a const object.

- A: `hits` is a `mutable` member, not a const object; modifying it is defined.
- B: `const_cast` by itself modifies nothing.
- C: `n` is not a const object; it is merely seen through a const access path. Modifying it after casting away const is defined ([[dcl.type.cv#3]]).
- D: `cfg.limit` is a non-`mutable` subobject of the const object `cfg`, so it is a const object too, and modifying it is undefined behavior.

One more spot that is easy to misjudge: `limit = 10` in the constructor body is fine. const semantics do not apply while the object is being constructed; they take effect only when the constructor for the most derived object ends ([[class.ctor.general#4]]).

`cfg` needs dynamic initialization, and Clang 23 does not place it in a read-only section, so no symptom shows up at run time. If `cfg` were constant-initialized, the compiler might put it in read-only memory and line D would crash outright.

</details>
</div>

## 3. Transparent replacement and std::launder

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program. `Point` has a `const` member.

```cpp run
#include <new>

struct Point {
    const int x;
    int y;
};

int main() {
    Point pt{1, 2};
    pt.~Point();
    ::new (&pt) Point{3, 4};
    return pt.x + pt.y;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed, with defined behavior (ok); it returns 7.**

1. By [[basic.life#9]], item 9.1, the original `pt` is transparently replaceable by the new object: both are complete objects, `pt` itself is not `const` (its member `x` is const, but the condition is about the complete object), the storage exactly overlays, and the types are the same.
2. So the name `pt` automatically refers to the new object ([[basic.life#10]]), and `pt.x` reads 3.
3. [[basic.life#12]] forbids creating a new object in the storage of a const complete object. `pt.x` is a const object, but not a complete object, so that restriction does not apply.

The usual reason for getting this wrong is remembering the old rule. Before C++20, for the old name to refer to the new object automatically, the original object's type also had to contain no non-static data member of const-qualified or reference type; otherwise you had to use `std::launder`, which C++17 introduced for this purpose (see [[CWG1776]]). C++20 removed that condition, and const and reference members no longer affect transparent replacement.

Change one thing, declare `pt` itself `const`, and the behavior is undefined:

```cpp run ub
#include <new>

struct Point {
    const int x;
    int y;
};

int main() {
    const Point pt{1, 2};
    ::new (const_cast<Point*>(&pt)) Point{3, 4};   // UB: pt is a const complete object
    return pt.x + pt.y;
}
```

This version violates [[basic.life#12]]. With Clang 23 at `-O0` it returns 3: the compiler assumes the value of the const object `pt` cannot change and uses the initial values 1 and 2 directly.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

Which of these four functions must be changed to use `std::launder` to have defined behavior? (The other three are defined as written.)

```cpp run
#include <new>

struct X { int n; };
struct Y { const int n; };

int a() { X* p = new X{1}; p->~X(); ::new (p) X{2}; int r = p->n; delete p; return r; }
int b() { const X* p = new const X{1}; ::new (const_cast<X*>(p)) const X{2}; int r = p->n; delete p; return r; }
int c() { X x{1}; ::new (&x) X{2}; return x.n; }
int d() { Y* p = new Y{1}; p->~Y(); ::new (p) Y{2}; int r = p->n; delete p; return r; }
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

All four functions create a new object of the same type in the storage of the original; they differ only in whether the original is transparently replaceable ([[basic.life#9]]). If it is, old pointers and names automatically refer to the new object ([[basic.life#10]]); if it is not, `std::launder` is needed to obtain a pointer to the new object (note 6 in [[basic.life#10]], [[ptr.launder#5]]).

- `a`: complete object, non-const, same type, exact overlay: transparently replaceable.
- `b`: the original object's type is `const X`, which violates item 9.1.1, so `p` does not point to the new object. `p->n` reads the original object whose lifetime has ended ([[basic.life#7]], item 7.2), and `delete p` has the same problem (item 7.1). Both must be written with `std::launder(p)`. The object has dynamic storage duration, so [[basic.life#12]] does not forbid creating a new object in its storage.
- `c`: a non-const object with automatic storage duration, transparently replaceable; `x` refers to the new object.
- `d`: `Y` has a const member, but since C++20 that does not affect transparent replacement (see the previous question).

`d` is the trap: in C++17 it really did need `launder`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program. This time a base class subobject is replaced.

```cpp run
#include <new>

struct Base { int v; };
struct Derived : Base { int extra; };

int main() {
    Derived d{{1}, 2};
    Base* pb = &d;
    ::new (pb) Base{5};
    return pb->v;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. Whether the new `Base` can become a subobject of `d` is governed by [[intro.object#2]]. Item 2.3 requires the original subobject not to be a potentially-overlapping subobject, and a base class subobject always is one ([[intro.object#7]]). So the new `Base` is a complete object.
2. It reuses part of `d`'s storage without being nested within `d`, so the lifetimes of the original base class subobject and of `d` itself both end ([[basic.life#2]], item 2.5).
3. Neither case of transparent replacement ([[basic.life#9]]) applies: the original is not a complete object, and the two are not corresponding direct subobjects. `pb` still points to the original base class subobject, whose lifetime has ended.
4. Accessing a non-static data member through such a pointer with `pb->v` is undefined behavior per [[basic.life#7]], item 7.2.

In our tests it returns 5 and nothing looks wrong. The note in [[ptr.launder#5]] summarizes the two situations that need `launder`: the complete object is const, or the original object is a base class subobject. The version below uses `launder` to get a pointer to the new object; to avoid touching the `Derived` whose lifetime has ended when the block exits, it lives in a byte array that provides storage:

```cpp run ok
#include <new>

struct Base { int v; };
struct Derived : Base { int extra; };

int main() {
    alignas(Derived) unsigned char buf[sizeof(Derived)];
    Derived* d = ::new (buf) Derived{{1}, 2};
    Base* pb = d;
    ::new (pb) Base{5};
    return std::launder(pb)->v;   // OK
}
```

</details>
</div>

## 4. How long temporaries live

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

What does the following program print?

```cpp run
#include <cstdio>

struct T {
    char c;
    T(char c) : c(c) {}
    ~T() { std::putchar(c); }
};

const T& pass(const T& t) { return t; }

int main() {
    const T& a = T('a');
    const T& b = pass(T('b'));
    T('c');
    std::putchar('|');
    (void)a; (void)b;
}
```

- A. `bc|a`
- B. `c|ba`
- C. `c|ab`
- D. `cb|a`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A. In our tests the output is `bc|a`.**

1. `T('a')` is materialized and bound directly to `a`, so its lifetime is extended to that of `a`, which ends when `main`'s block exits ([[class.temporary#6]], item 6.1). So `a` is printed after `|`.
2. `T('b')` is bound to the reference parameter of `pass`. That is an exception to the extension rule: the temporary persists only until the end of the full-expression containing the call ([[class.temporary#6]], item 6.10). `b` is bound to the reference returned by `pass`, not to the temporary itself, so `b` dangles from the next statement on. `b` is printed at the end of the second statement.
3. `T('c');` is a discarded-value expression; a class prvalue is materialized there (note 2 in [[class.temporary#2]]) and destroyed at the end of the full-expression ([[class.temporary#4]]).
4. Then `|` is printed, and finally the block exits and the temporary bound to `a` is destroyed.

B and C both assume that the temporary for `b` is extended too, which is the misconception this question targets: a reference extends only a temporary bound directly to it; with a function call in between, there is no extension. The final `(void)b` does not read the object's value, so it is not undefined behavior by itself.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

Let `struct S { int v; const int& ref() const { return v; } };`, and let `cond` be a `bool` variable. Which of the four declarations below leaves a dangling reference once the declaration is complete?

- A. `const int& a = S{1}.v;`
- B. `const int& b = static_cast<const int&>(S{2}.v);`
- C. `const int& c = S{3}.ref();`
- D. `const int& d = cond ? S{4}.v : S{5}.v;`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

[[class.temporary#6]] lists the expression forms through which a temporary's lifetime can be passed on to a reference: the temporary materialization itself, wrapped in parentheses, array subscripting, `.` access to a data member of non-reference type, the four named casts without a user-defined conversion, conditional expressions, comma expressions, and so on. The glvalue the reference finally binds to must be obtained through one of these forms.

- A: `S{1}` materializes a temporary, `.v` accesses a member of non-reference type (item 6.4), and the whole temporary is extended.
- B: `static_cast` turns a glvalue referring to the member into a glvalue referring to the same object, without a user-defined conversion (item 6.6.2): extended.
- C: `ref()` is a function call, which is not in the list. The returned reference refers to a member of the temporary, but the temporary is destroyed at the end of the full-expression, and `c` dangles.
- D: both branches are xvalues of type `int`, the conditional expression is a glvalue, and its second and third operands are of the listed forms (item 6.8). Only the evaluated branch creates a temporary, and that temporary is extended.

Running under ASan in our tests, reading `c` reports `stack-use-after-scope`; the other three report nothing. Case D is the third line of example 2 in [[class.temporary#6]]. For more dangling scenarios see [[topics/dangling-references]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program. What is returned is a static variable.

```cpp run
const long& counter() {
    static int n = 0;
    ++n;
    return n;
}

int main() { return counter(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed (error).**

1. The return type is `const long&`, while `n` is an `int`; the two types are not reference-related. By [[dcl.init.ref#5]], item 5.4.2, the initializer is first converted to a prvalue of type `long` and then materialized, and the reference binds to that temporary `long`, not to `n`.
2. [[stmt.return#6]] says that a return statement that binds the returned reference to a temporary object makes the program ill-formed. This is the rule since C++26 adopted [[P2748R5]]; before that, the code compiled and returned a dangling reference.

`static` is a distractor. `n` does live throughout, but the reference never binds to it. Clang 23 reports the error `returning reference to local temporary object` with `-std=c++2c`, and only a warning with the same text under `-std=c++23`, matching the change between standard versions. Changing the return type to `const int&` makes it well-formed.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
#include <string>

struct Config {
    const std::string& name;
    Config() : name("default") {}
};

int main() {
    Config c;
    return c.name.size() == 7 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed (error).**

`"default"` must first be converted to a `std::string` temporary, and the reference member `name` binds to it. [[class.base.init#8]] says that a temporary expression bound to a reference member in a mem-initializer makes the program ill-formed.

Why not just extend the lifetime? The temporary is created in the constructor's mem-initializer, and there is no way to make it live as long as the `Config` object; if it were destroyed at the end of the full-expression as usual, `name` would dangle from birth. The standard chooses to reject such code outright. Default member initializers have the same rule ([[class.base.init#13]]), but the error is only issued when some constructor actually uses the initializer.

Clang 23 reports `reference member 'name' binds to a temporary object whose lifetime would be shorter than the lifetime of the constructed object`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program. `Ref` is an aggregate, initialized with parentheses.

```cpp run
struct Ref {
    const int& r;
};

int main() {
    Ref x(42);
    return x.r;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. When an aggregate is initialized from a parenthesized expression-list (C++20, [[P0960R3]]), a temporary bound to a reference member persists only until the end of the full-expression containing the expression-list ([[class.temporary#6]], item 6.11).
2. So after the declaration `x.r` dangles, and `return x.r` reads an object whose lifetime has ended; the behavior is undefined ([[basic.life#8]], item 8.1).

Replacing the parentheses with braces makes it defined:

```cpp run ok
struct Ref {
    const int& r;
};

int main() {
    Ref x{42};       // OK: the temporary's lifetime is extended to that of x.r
    return x.r;      // returns 42
}
```

Brace aggregate initialization binds the reference member directly to the materialized temporary, and the ordinary extension rule applies. The parenthesized form was designed to behave like a constructor call, and a constructor's reference parameter does not extend the lifetime of a temporary argument either (item 6.10). Clang 23 gives a `-Wdangling` warning for the original program, and ASan reports `stack-use-after-scope` at run time.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program (per the current draft).

```cpp run
#include <vector>

struct Holder {
    std::vector<int> v{1, 2, 3};
    const std::vector<int>& get() const { return v; }
};

Holder make() { return {}; }

int main() {
    int sum = 0;
    for (int x : make().get())
        sum += x;
    return sum == 6 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed, with defined behavior (ok). In C++20 and earlier it is undefined behavior.**

1. A range-based for is equivalent to first initializing an `auto&&` reference with the for-range-initializer and then obtaining iterators from it ([[stmt.ranged#1]]). Here the reference binds to the reference returned by `get()`; the `Holder` temporary produced by `make()` is not bound directly to it.
2. In C++20 that temporary is destroyed at the end of the initializer's full-expression, and the loop iterates over a member of a destroyed object: undefined behavior.
3. Since C++23, [[class.temporary#7]] has a special case: every temporary created in a for-range-initializer that would otherwise be destroyed at the end of that full-expression persists until the end of the lifetime of the reference the initializer initializes, that is, until the loop ends ([[P2718R0]]).

With Clang 23 and `-std=c++2c`, an ASan run reports nothing; compiled with `-std=c++20`, ASan reports `stack-use-after-scope`.

The special case covers only temporaries. `f2(g())` in example 2 of [[stmt.ranged#1]] is still undefined behavior: `f2` takes its parameter by value and returns a reference to the parameter, and a parameter is not a temporary. Whether a parameter is destroyed when the function returns or at the end of the full-expression is implementation-defined ([[expr.call#7]]); either way, it happens before the loop starts. For the full story see [[papers/range-for-temporaries]].

</details>
</div>

## 5. Accessing an object's value, and synthesis

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Which of the following is a trivially copyable type?

- A. `struct A { int x; virtual ~A() = default; };`
- B. `struct B { int x; B() = default; B(const B&) = delete; B(B&&) = delete; B& operator=(const B&) = delete; B& operator=(B&&) = delete; };`
- C. `struct C { int x; C() = default; C(const C& o) : x(o.x) {} };`
- D. `struct D { const int x; int& r; };`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

[[class.prop#1]] requires a trivially copyable class to satisfy three conditions at once: it has at least one eligible copy/move constructor or copy/move assignment operator; each such eligible function is trivial; and it has a trivial, non-deleted destructor. Eligible means not deleted, constraints satisfied, and no more-constrained function of the same kind ([[special#6]]).

- A: it has a virtual function, so the copy constructor and the others are not trivial (and a virtual destructor is not trivial either).
- B: all four copy/move functions are deleted, so none is eligible, violating item 1.1.
- C: the copy constructor is user-provided, hence not trivial.
- D: the `const` member and the reference member make copy assignment and move assignment defined as deleted, so they are no longer eligible; the implicit copy and move constructors are still eligible and trivial, and the destructor is trivial. All three conditions hold.

D looks the least likely because it cannot be assigned. But trivially copyable only requires the eligible operations that exist to be trivial; it does not require every operation to be available. For such objects, [[basic.types.trivial#4]] guarantees that after the underlying bytes of one object are copied into another with `memcpy`, the latter holds the former's value representation.

With Clang 23, `std::is_trivially_copyable_v<B>` yields `true`, which disagrees with [[class.prop#1]], item 1.1. The "at least one eligible function" requirement is discussed in [[CWG1734]]. The results for the other three match the standard.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program. The union's active member is currently `raw`, and `Pair` has a user-provided default constructor.

```cpp run
struct Pair {
    int first;
    int second;
    Pair() : first(0), second(0) {}
};

union Storage {
    int raw;
    Pair pair;
    Storage() : raw(0) {}
};

int main() {
    Storage s;
    s.pair.first = 1;
    return s.pair.first;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. Assigning to a union member can change the active member, but the rule covers only certain left operands ([[class.union.general#5]]). For `E1 = E2`, the set of subexpressions S(E1) is computed first, and only members in that set are implicitly created.
2. `s.pair.first` has the form `A.B` with `A` being `s.pair`, and `first` is not a union member, so S(`s.pair.first`) is S(`s.pair`).
3. S(`s.pair`) contains `s.pair` only if the type of `pair` is a non-class, non-array type, or a class type with a trivial default constructor that is not deleted. `Pair`'s default constructor is user-provided and not trivial, so the set is empty and the assignment does not begin the lifetime of `s.pair`.
4. So `s.pair.first = 1` modifies an object outside its lifetime, which is undefined behavior per [[basic.life#8]], item 8.1; [[class.union.general#2]] also implies that the active member is still `raw`.

The trap is that `Pair` is an implicit-lifetime type (its copy constructor is trivial, [[class.prop#8]], item 8.2), but the union-assignment rule does not look at implicit lifetime; it looks at whether the default constructor is trivial. Remove `Pair`'s constructor and the program is defined; if the constructor stays, the correct approach is placement new:

```cpp run ok
#include <new>

struct Pair {
    int first;
    int second;
    Pair() : first(0), second(0) {}
};

union Storage {
    int raw;
    Pair pair;
    Storage() : raw(0) {}
};

int main() {
    Storage s;
    ::new (&s.pair) Pair;   // changes the active member (note in [class.union.general]/6)
    s.pair.first = 1;       // OK
    return s.pair.first;
}
```

Both versions return 1 in our tests, and the sanitizers report nothing. The `X` with a const member in example 2 of [[class.union.general#5]] is the same idea: its default constructor is deleted, so the assignment `y.x.b` likewise does not begin the lifetime of `y.x`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge the whole program.

```cpp run
#include <cstdio>

int main() {
    int x = 0x01020304;
    auto* p = reinterpret_cast<signed char*>(&x);
    std::printf("%d\n", *p);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior (ub).**

1. The conversion does not change the pointer value of `p`; it still points to the `int` object `x` ([[expr.static.cast#12]]), and `*p` is an lvalue of type `signed char` referring to `x`.
2. [[basic.lval#11]] says an object whose dynamic type is `int` may be accessed only through a glvalue whose type is similar to one of: `int` itself, the corresponding signed or unsigned type (`int`, `unsigned int`), or `char`, `unsigned char`, `std::byte`.
3. `signed char` is not on the list. Reading `*p` accesses the stored value of the object through a type that is not accessible, and the behavior is undefined.

Replace `signed char` with `char` or `unsigned char` and the access itself is permitted (item 11.3). The corresponding C rule allows any character type, including `signed char`; C++ lists only three, a subtle difference between the two languages.

In our tests it prints `4` and the sanitizers report nothing. Mainstream compilers' alias analysis typically treats every character type as able to alias any object, so in practice no difference is visible; by the standard, though, the program is undefined. For what value is actually read, see question 24.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

Judge the whole program. `p` takes part in a comparison after it has been `delete`d.

```cpp run
#include <cstdio>

int main() {
    int* p = new int(1);
    int* q = p;
    delete p;
    std::printf("%d\n", p == q);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: implementation-defined (impl).**

1. `delete p` deallocates the storage, ending the duration of that region of storage ([[basic.stc.dynamic.deallocation#5]]). From then on, the values of `p` and `q` are pointer values that are invalid in the current evaluation ([[basic.compound#6]]).
2. Reading the variables `p` and `q` is fine in itself: they are pointer objects that are still alive, and the lvalue-to-rvalue conversion simply yields the value they hold ([[conv.lval#3]], item 3.4.3).
3. Comparing invalid pointer values for equality is implementation-defined per [[basic.compound#6]], item 6.2.2. Only indirection (dereferencing) is undefined behavior (item 6.1).

In our tests it prints `1`. The tempting wrong answer is `ub`: many people believe that touching a dangling pointer at all is undefined behavior. The current draft draws finer lines: dereferencing is undefined behavior; comparing, converting to `bool` and doing arithmetic are implementation-defined; merely reading and copying is defined.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`Base` is a trivially copyable type. The `assign` below uses `memcpy` to assign to a `Base&`, but what is passed in is the base class subobject of a `Derived`. Explain whether the standard guarantees that this code changes only the `Base` part of `d`, and why Clang 23 prints `8 8 2 0`.

```cpp run
#include <cstdio>
#include <cstring>
#include <type_traits>

class Base {
    int  id_;
    char kind_;
public:
    Base(int id, char kind) : id_(id), kind_(kind) {}
    int id() const { return id_; }
    char kind() const { return kind_; }
};

struct Derived : Base {
    char tag;
    Derived(int id, char kind, char t) : Base(id, kind), tag(t) {}
};

static_assert(std::is_trivially_copyable_v<Base>);

void assign(Base& dst, const Base& src) {
    std::memcpy(&dst, &src, sizeof(Base));
}

int main() {
    Derived d(1, 'a', 'T');
    assign(d, Base(2, 'b'));
    std::printf("%zu %zu %d %d\n", sizeof(Base), sizeof(Derived), d.id(), d.tag == 'T');
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key point: the standard does not guarantee it. The byte-copying guarantees in [[basic.types.trivial#3]] and [[basic.types.trivial#4]] explicitly exclude potentially-overlapping subobjects, and a base class subobject is one.**

1. Base class subobjects and `[[no_unique_address]]` members are potentially-overlapping subobjects ([[intro.object#7]]). Their `sizeof` is their size as a complete object, but as subobjects their trailing padding bytes may be taken over by the derived class or by adjacent members to hold other data.
2. Clang 23 follows the Itanium C++ ABI: `Base` has private data members, so it is not a POD in the C++03 sense, and its tail padding may be reused. `Base` occupies 8 bytes (4 bytes `id_`, 1 byte `kind_`, 3 bytes padding), and `Derived::tag` is placed in those 3 padding bytes, so `sizeof(Derived)` is also 8.
3. `memcpy(&dst, &src, sizeof(Base))` copies 8 bytes, writing `src`'s padding bytes into `d` as well and overwriting `tag`. So `d.id()` becomes 2 and `d.tag == 'T'` becomes false.
4. This is exactly why [[basic.types.trivial#3]] adds the qualification "not a potentially-overlapping subobject": for such a subobject, not all of its `sizeof` bytes necessarily belong to it.

Conclusion: trivially copyable only guarantees bytewise copying for complete objects and ordinary member subobjects. For a base class subobject or a `[[no_unique_address]]` member, use its copy assignment operator (`static_cast<Base&>(d) = src`); the compiler-generated trivial assignment knows which bytes belong to it.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

The two lines below try to inspect the object representation of an `int` byte by byte. Going strictly by the current draft's wording, is each of the lines marked (1) and (2) defined? If so, which rule determines the value read?

```cpp run
#include <cstdio>

int main() {
    int x = 0x01020304;
    auto* p = reinterpret_cast<unsigned char*>(&x);
    unsigned b0 = *p;         // (1)
    unsigned b1 = *(p + 1);   // (2)
    std::printf("%u %u\n", b0, b1);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key point: the access in (1) is permitted, but by the letter of the wording what it reads is the `unsigned char` value congruent to the value of `x`, not the contents of the byte at that address; (2) is, by the letter, undefined behavior. The current draft does not really support reading an object representation byte by byte, which is a known defect.**

1. After the conversion, `p` still points to the `int` object `x` ([[expr.static.cast#12]]), because there is no `unsigned char` object at `x`'s location that is pointer-interconvertible with it.
2. (1): `*p` is an `unsigned char` lvalue referring to `x` ([[expr.unary.op#1]]). Accessing an `int` object through `unsigned char` is permitted by [[basic.lval#11]], item 11.3. The result of the read is determined by [[conv.lval#3]], item 3.4.1: take the value V held in the object (an `int` value); the result is the `unsigned char` value congruent to V, which is `0x01020304` modulo 256, that is 4, regardless of what that byte actually contains in memory.
3. (2): in `p + 1`, `p` has type `unsigned char*`, while the object it points to, `x` (treated as the element of a one-element array `int[1]` per [[basic.compound#3]]), has type `int`. The two are not similar, and [[expr.add#6]] says the behavior is undefined. Even setting that aside, `p + 1` could only yield a past-the-end pointer, which cannot be dereferenced. The same reasoning applies to adding 0: if (1) were written `p[0]`, that is by definition `*(p + 0)` ([[expr.sub#2]]), and the addition also falls under [[expr.add#6]], making it undefined behavior too.
4. [[basic.types.general#2]] defines the object representation as the N `unsigned char` objects taken up by the object, but no rule makes those `unsigned char` objects actually exist at `x`'s location, and no rule lets a pointer move between them.

In our tests it prints `4 3`; every implementation treats such code the way programmers expect, and library facilities such as `memcpy` and `std::bit_cast` rely on it. [[P1839R7]] (Accessing object representations) tries to fix this defect by making the object representation a real array that can be traversed through `unsigned char*`; as of the current draft it has not been merged. To obtain the bytes portably, use `std::bit_cast<std::array<unsigned char, sizeof(int)>>(x)` or `memcpy` into an `unsigned char` array; both have well-defined semantics ([[basic.types.trivial#3]]).

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

Below is a simplified `Optional<T>`. Answer three questions: (a) is there a problem with `operator*`, and how should it be fixed; (b) what happens when an `Optional` holding a `std::string` is copied with the compiler-generated copy constructor; (c) if `T`'s constructor throws inside `emplace`, what state is the object in, and is there undefined behavior?

```cpp run
#include <cstddef>
#include <new>
#include <string>
#include <utility>

template<class T>
class Optional {
    alignas(T) std::byte buf_[sizeof(T)];
    bool engaged_ = false;

public:
    Optional() = default;
    ~Optional() { reset(); }

    template<class... Args>
    T& emplace(Args&&... args) {
        reset();
        ::new (buf_) T(std::forward<Args>(args)...);
        engaged_ = true;
        return **this;
    }

    void reset() {
        if (engaged_) {
            (**this).~T();
            engaged_ = false;
        }
    }

    T& operator*() { return *reinterpret_cast<T*>(buf_); }
};

int main() {
    Optional<std::string> a;
    a.emplace(40, 'x');
    a.emplace("short");
    return *a == "short" ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key points: (a) it needs `std::launder`; (b) the copied `Optional` claims to hold an object, but there is no `std::string` object in it, and its destruction is undefined behavior; (c) after the exception the object is empty, and there is no undefined behavior.**

(a) Same as question 4. `buf_` is a `std::byte` array and provides storage for the `T` created by placement new ([[intro.object#3]]), but the result of `reinterpret_cast<T*>(buf_)` still points to `buf_[0]` ([[expr.static.cast#12]]). Accessing the `T` through it violates [[basic.lval#11]], and calling member functions and the destructor through it violates the restrictions of [[basic.life#7]] (`buf_[0]` is not a `T`). Change it to `*std::launder(reinterpret_cast<T*>(buf_))`: there is now a `T` within its lifetime at that address, satisfying [[ptr.launder#2]]. Another fix is to store the pointer returned by placement new in `emplace` and use it from then on, at the cost of storing an extra pointer. The site's [[ptr.launder]] page has the same example.

(b) The implicit copy constructor copies `buf_` element by element, copying only bytes. Objects are implicitly created when the new array's lifetime begins ([[intro.object#16]]), but only objects of implicit-lifetime types, and `std::string` is not one, so there is no `std::string` in the copy's `buf_`. Yet the copy's `engaged_` is `true`, and its destructor will call a destructor on a `std::string` that does not exist, which is undefined behavior ([[basic.life#7]], item 7.2). In practice, if the string is long enough to use a heap buffer, the two `Optional`s share the same buffer, and in our tests ASan reports `attempting double-free`. You must define the copy and move operations yourself and copy-construct the `T` in the destination with placement new.

(c) `emplace` calls `reset()` first, so `engaged_` is already `false`; when `T`'s constructor then throws, the new-expression leaves no object behind and the exception propagates out of `emplace`. The `Optional` is now empty, and its destructor does not try to destroy a `T` because `engaged_ == false`. `buf_` is a `std::byte` array with a trivial destructor, so the [[basic.life#11]] problem from question 8 does not arise here. What this code gives is the basic exception-safety guarantee: after a failure the object is valid but empty, and the old value is lost. If the old value must survive a failure, the new value has to be constructed somewhere else first, which is the idea behind the fixed version in question 8.

</details>
</div>

## Questions and clauses

| No. | Topic | Clauses |
|---|---|---|
| 1 | `malloc` implicitly creating an aggregate with a non-trivial member | [[intro.object#13]], [[c.malloc#4]], [[class.prop#8]] |
| 2 | Storage duration of an object created by placement new | [[basic.stc.general#2]], [[expr.new#10]], [[basic.stc.auto#1]] |
| 3 | `[[no_unique_address]]` and address uniqueness | [[intro.object#8]], [[intro.object#10]] |
| 4 | Implicit objects in a byte array and `reinterpret_cast` | [[intro.object#16]], [[expr.static.cast#12]], [[basic.lval#11]] |
| 5 | `char` arrays do not provide storage | [[intro.object#3]], [[basic.life#2]], [[basic.life#11]] |
| 6 | Reusing storage without calling the destructor | [[basic.life#6]], [[basic.life#9]], [[basic.life#10]] |
| 7 | Storage is reused before the new-initializer is evaluated | [[basic.life#2]], [[basic.life#8]] |
| 8 | An exception while rebuilding after destruction | [[basic.life#11]], [[class.dtor#18]] |
| 9 | Modifying const objects, and `mutable` | [[dcl.type.cv#4]], [[basic.type.qualifier#1]], [[class.ctor.general#4]] |
| 10 | Transparent replacement of an object with a const member | [[basic.life#9]], [[basic.life#12]] |
| 11 | When `std::launder` is required | [[basic.life#9]], [[ptr.launder#5]] |
| 12 | Replacing a base class subobject | [[intro.object#2]], [[basic.life#7]], [[basic.life#9]] |
| 13 | When temporaries are destroyed | [[class.temporary#4]], [[class.temporary#6]] |
| 14 | Which expression forms pass on lifetime extension | [[class.temporary#6]] |
| 15 | A return statement binding a temporary | [[stmt.return#6]], [[dcl.init.ref#5]] |
| 16 | A reference member bound to a temporary in a mem-initializer | [[class.base.init#8]] |
| 17 | Reference members in parenthesized aggregate initialization | [[class.temporary#6]] |
| 18 | Temporaries in a range-based for initializer | [[class.temporary#7]], [[stmt.ranged#1]] |
| 19 | Deciding trivial copyability | [[class.prop#1]], [[special#6]] |
| 20 | Assignment to union members and the active member | [[class.union.general#5]], [[basic.life#8]] |
| 21 | Accessing an object through `signed char` | [[basic.lval#11]] |
| 22 | Comparing invalid pointer values | [[basic.compound#6]], [[conv.lval#3]] |
| 23 | Potentially-overlapping subobjects and `memcpy` | [[basic.types.trivial#3]], [[intro.object#7]] |
| 24 | Reading an object representation byte by byte | [[basic.lval#11]], [[conv.lval#3]], [[expr.add#6]] |
| 25 | Storage management in a home-made `Optional` | [[intro.object#3]], [[ptr.launder#2]], [[basic.life#7]] |
