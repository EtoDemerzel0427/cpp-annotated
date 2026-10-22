---
title: Stack unwinding
summary: "Which objects are destroyed as an exception travels to its handler: fully constructed automatic objects are destroyed in reverse order; when construction fails halfway only the already-initialized subobjects are destroyed and the object's own destructor does not run; when a delegating constructor's body throws, the destructor runs; a new-expression returns the memory."
updated: 2026-10-19
---

!!! tldr
    - As an exception travels to its handler, the automatic objects constructed since entry into that try block and not yet destroyed are destroyed in reverse order of the completion of their construction. This is called stack unwinding, and it is the normative basis of RAII.
    - When a constructor throws, the object's own destructor does not run; the bases and members already initialized are destroyed. So every resource should be managed by its own subobject.
    - When a destructor body throws, the members and bases are still destroyed as usual; nothing leaks.
    - When the body of a delegating constructor throws, the object is already fully constructed, and the standard calls the destructor of the whole object.
    - When a constructor throws in a `new` expression, the matching `operator delete` is called to return the memory.

## Which objects unwinding destroys (¶1–¶2)

```cpp run title="unwind-order.cpp" ok
#include <cstdio>

struct T {
    const char* n;
    explicit T(const char* s) : n(s) { std::printf("+%s ", n); }
    ~T() { std::printf("-%s ", n); }
};

void f() {
    T a("a");
    T b("b");
    throw 0;
    T c("c");          // never constructed, never destroyed
}

int main() {
    T outer("outer");  // outside the try block, not involved in unwinding
    try {
        T t("t");
        f();
    } catch (int) {
        std::printf("| handler ");
    }
    std::printf("| after\n");
}
```

The output is `+outer +t +a +b -b -a -t | handler | after`, and finally `-outer`.

¶1 As control passes from the throw point to a handler, objects are destroyed as specified in this subclause; this process is called [[g:stack-unwinding]].

¶2 Each object with automatic storage duration that has been fully constructed since the try block (the one that catches the exception) was entered, and not yet destroyed, is destroyed, in reverse order of the completion of their construction. Objects constructed earlier outside the try block are not affected. An object under construction is not fully constructed; its subobjects are handled by ¶3.

Whether control leaves a scope normally or because of an exception, the constructed objects are destroyed, and only they are. This is why C++ needs no `finally`.

Whether the stack is unwound when no matching handler is found is implementation-defined; when the search leaves a `noexcept` function, the stack may be only partially unwound ([[except.terminate#2]]).

### Throwing after return: the returned object must be destroyed too

The second sentence of ¶2 handles a rare case: a `return` statement has already constructed the returned object, and then an exception is thrown while destroying local variables; the returned object must then be destroyed as well.

```cpp title="return-then-throw.cpp"
#include <cstdio>

struct A {
    int id;
    explicit A(int i) : id(i) { std::printf("A%d() ", id); }
    ~A() { std::printf("~A%d ", id); }
};
struct Y { ~Y() noexcept(false) { throw 0; } };

A f() {
    try {
        A a(1);
        Y y;
        A b(2);
        return A(3);    // #1: the returned object A3 is constructed, then b is destroyed
    } catch (...) {     //     destroying y throws, and unwinding begins
    }
    return A(4);        // #2: the returned object is constructed again
}

int main() { A r = f(); std::printf("| got A%d\n", r.id); }
```

The returned object is constructed when the operand of `return` is evaluated, before the local variables are destroyed ([[stmt.return]]). It is the last object fully constructed in the try block, so it is the first destroyed during unwinding. Per the standard, the output should be `A1() A2() A3() ~A2 ~A3 ~A1 A4() | got A4`.

!!! impl "Compiler status"
    Clang 23 prints `A1() A2() A3() ~A2 ~A1 A4() | got A4`, missing `~A3`: the returned object leaks. This is a long-standing nonconformance in Clang (corresponding to CWG2176). Because the implementation does not match the standard, this code carries no verdict.

## Construction failing halfway (¶3)

```cpp run title="partial-construction.cpp" ok
#include <cstdio>

struct M {
    const char* n;
    M(const char* s, bool fail = false) : n(s) {
        if (fail) throw 1;
        std::printf("+%s ", n);
    }
    ~M() { std::printf("-%s ", n); }
};

struct Base {
    M m{"Base::m"};
    ~Base() { std::printf("~Base "); }
};

struct X : Base {
    M a{"a"};
    M b{"b", true};    // throws while constructing b
    M c{"c"};          // construction never starts
    X() { std::printf("X-body "); }
    ~X() { std::printf("~X "); }        // never called
};

int main() {
    try { X x; } catch (int) { std::printf("| caught\n"); }
}
```

The output is `+Base::m +a -a ~Base -Base::m | caught`. `Base` and `a` were fully constructed and are destroyed; `b`'s constructor did not complete and `c` never started, so neither is destroyed. `X`'s constructor did not complete, the lifetime of the `X` object never began ([[basic.life]]), and `~X` does not run.

¶3 If the initialization of an object (other than by a delegating constructor, see ¶4) is terminated by an exception, the destructor is invoked for each of its subobjects that is **known to be initialized** and whose initialization has completed. They are destroyed in reverse order of the completion of their construction, and this happens before entry into a handler of the constructor's function-try-block, if any.

It follows that `new`ing two raw pointers in a constructor leaks:

```cpp title="ctor-leak.cpp" ok
#include <memory>

struct Leaky {
    int* p;
    int* q;
    Leaky() : p(new int[100]), q(new int[100]) {}   // when the second new throws:
    ~Leaky() { delete[] p; delete[] q; }            // ~Leaky does not run, and p leaks
};

struct Safe {
    std::unique_ptr<int[]> p;
    std::unique_ptr<int[]> q;
    Safe() : p(new int[100]), q(new int[100]) {}    // when q fails, p is fully constructed and is destroyed
};
```

`Leaky` is well-formed; it just leaks. Hand each resource to a subobject to manage, and ¶3 does the cleanup automatically.

### Known to be initialized

A subobject is [[g:known-to-be-initialized]] if it is not an anonymous union member and its initialization is specified by one of:

- ¶3.1 a constructor initializing bases and members ([[class.base.init]]);
- ¶3.2 a defaulted copy or move constructor ([[class.copy.ctor]]);
- ¶3.3 an inherited constructor ([[class.inhctor.init]]);
- ¶3.4 aggregate initialization ([[dcl.init.aggr]]);
- ¶3.5 initialization of the closure object when a lambda expression is evaluated ([[expr.prim.lambda.capture]]);
- ¶3.6 default-initialization, value-initialization or direct-initialization of an array ([[dcl.init.general]]).

The qualifier "known" is there because for some subobjects the language cannot know whether they have been constructed. The typical case is a **variant member**, that is, a member of a union: which member is active is usually known only to the programmer. Note 2 explains that a variant member is known to be initialized only if it is explicitly named by a *mem-initializer* or a designated initializer, or has a default member initializer. For a complete object, virtual base class subobjects are included too.

Aggregates and arrays have no constructors, but the rule applies to them just the same:

```cpp run title="aggregate-partial.cpp" ok
#include <cstdio>

struct M {
    int i;
    M(int x) : i(x) { if (x == 3) throw x; std::printf("+%d ", i); }
    ~M() { std::printf("-%d ", i); }
};

struct Agg { M a, b, c; };

int main() {
    try { Agg g{1, 2, 3}; } catch (int) { std::printf("| agg\n"); }
    try { M arr[4] = {1, 2, 3, 4}; } catch (int) { std::printf("| array\n"); }
}
```

The output is `+1 +2 -2 -1 | agg` and `+1 +2 -2 -1 | array`.

For ¶3 to be executable, a constructor must be able to call the destructor of every subobject. So [[class.base.init]] specifies that a non-delegating constructor potentially invokes the destructor of each subobject of class type. If such a destructor is deleted or inaccessible, the program is ill-formed even if the constructor body cannot possibly throw:

```cpp title="dtor-needed-by-ctor.cpp" error
struct NoDtor {
    NoDtor() = default;
    ~NoDtor() = delete;
};

struct Holder {
    NoDtor d;
    Holder() {}         // error: the constructor needs NoDtor's destructor
};
```

Note 1 points out a corollary: if an object has a reference member that extends the lifetime of some temporary, then when the object's initialization fails, the lifetime of that reference member ends, and the temporary is destroyed with it:

```cpp run title="ref-member-temp.cpp" ok
#include <cstdio>

struct Tmp { ~Tmp() { std::puts("~Tmp"); } };
struct Thrower { Thrower() { throw 0; } };

struct Agg {
    const Tmp& r;      // bound to a temporary during aggregate initialization, extending its lifetime
    Thrower t;
};

int main() {
    try { Agg a{Tmp{}, {}}; (void)a; } catch (int) { std::puts("caught"); }
}
```

It prints `~Tmp`, then `caught`.

## Destruction failing halfway (¶3)

```cpp run title="dtor-throws.cpp" ok
#include <cstdio>

struct M { const char* n; ~M() { std::printf("-%s ", n); } };
struct B { ~B() { std::printf("~B "); } };

struct D : B {
    M m1{"m1"}, m2{"m2"};
    ~D() noexcept(false) { std::printf("~D-body "); throw 0; }
};

int main() {
    try { D d; } catch (int) { std::printf("| caught\n"); }
}
```

The output is `~D-body -m2 -m1 ~B | caught`.

The second half of ¶3 specifies that if a destructor is terminated by an exception, the destructor calls that would have followed the body (for members, direct bases, and, for a complete object, virtual bases, see [[class.dtor]]) and have not yet started are still executed. So a throwing destructor body does not make members and bases leak. This can only happen with a `noexcept(false)` destructor.

## Delegating constructors (¶4)

```cpp run title="delegating.cpp" ok
#include <cstdio>

struct S {
    int* p;
    explicit S(int n) : p(new int[n]) { std::puts("target ctor done"); }
    S() : S(4) {                    // delegates to S(int)
        std::puts("delegating body");
        throw 42;                   // the object is fully constructed: ~S() is called
    }
    ~S() { std::puts("~S frees p"); delete[] p; }
};

int main() {
    try { S s; } catch (int) { std::puts("caught"); }
}
```

The output is `target ctor done`, `delegating body`, `~S frees p`, `caught`, and running it with `-fsanitize=address` reports no leaks.

¶4 If the body of a delegating constructor ([[class.base.init]]) exits via an exception, the object's destructor is invoked, before entry into a handler of the delegating constructor's function-try-block. When the target constructor returns, all bases and members have been initialized and the object is structurally complete, so running the destructor is safe; destroying subobjects one by one would instead skip the cleanup in the destructor body.

This gives an idiom: first delegate to a constructor that cannot fail, putting the object into a destructible state, then do the work that might fail in the delegating constructor's body. On failure, the destructor does the cleanup. If the exception occurs inside the target constructor, ¶3 applies to the target constructor and the destructor does not run.

## A new-expression returns the memory (¶5)

```cpp run title="new-dealloc.cpp" ok
#include <cstdio>
#include <new>

struct X {
    X() { throw 1; }
    static void* operator new(std::size_t n) {
        std::puts("X::operator new");
        return ::operator new(n);
    }
    static void operator delete(void* p) noexcept {
        std::puts("X::operator delete");
        ::operator delete(p);
    }
};

int main() {
    try { new X; } catch (int) { std::puts("caught"); }
}
```

The output is `X::operator new`, `X::operator delete`, `caught`.

¶5 is a note: if the object was allocated by a *new-expression*, the matching deallocation function is called to free the storage. The normative rule is in [[expr.new]]: if no unambiguous matching deallocation function can be found, the memory is not freed. For placement new, the matching one is the placement `operator delete` with the corresponding parameters, which is called only in this situation.

## Implementation

!!! impl "How compilers implement stack unwinding"
    Under the Itanium C++ ABI, the compiler generates a **landing pad** for each call site that might throw; it destroys the objects already constructed in this frame and then calls `_Unwind_Resume` to continue unwinding. The mapping from call sites to landing pads is recorded in a read-only exception table. The run-time state "fully constructed" is encoded statically by the compiler as call-site ranges: if a call site lies after the construction of `a` and before that of `b`, its landing pad destroys only `a`. Partial construction in constructors is implemented the same way. See [[toolchain/exception-implementation]] for details.

## Questions

!!! question "Question 1"
    When the constructor of `U` below throws, is `s` destroyed?

    ```cpp
    struct U {
        union { std::string s; int i; };
        U() : s("hello") { throw 0; }
        ~U() {}
    };
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. `s` is a member of an anonymous union and therefore a variant member of `U`. It is explicitly named by a *mem-initializer*, its initialization is specified by [[class.base.init]] and has completed, so it is known to be initialized (Note 2). `i` is not named and is not destroyed.

The anonymous union member that ¶3 excludes is the unnamed union object inside `U` itself. Its destructor is deleted because of the `std::string` member and cannot be called. Clang 23 behaves accordingly.
</details>

!!! question "Question 2"
    Given the delegation chain `A() : A(1) {}`, `A(int) : A(1, 2) { throw 0; }`, `A(int, int) {}`: when the body of the middle constructor throws, is `~A()` called?

<details markdown="1">
<summary>Answer</summary>

Yes. `A(int)` is itself a delegating constructor, and its target `A(int, int)` has returned, so the object is fully constructed and `~A()` is called per ¶4. The exception then continues out of `A()`.
</details>

## Summary

| Situation | What is destroyed | Source |
|---|---|---|
| An exception passes through a block scope | automatic objects constructed since entering the try block, in reverse order | ¶2 |
| Destroying local variables throws after `return` | the already-constructed returned object too | ¶2 |
| Non-delegating initialization throws midway | subobjects known to be initialized whose initialization completed; the object's own destructor does not run | ¶3 |
| A destructor body throws | members and bases not yet destroyed are destroyed as usual | ¶3 |
| A delegating constructor body throws | the object's destructor | ¶4 |
| Construction of an object created by `new` fails | the matching deallocation function is called | ¶5, [[expr.new]] |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The stable name `[except.ctor]` of this subclause comes from its early title, Constructors and destructors; its current title is Stack unwinding.

</details>
