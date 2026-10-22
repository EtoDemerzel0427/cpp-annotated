---
title: Storage duration
summary: "How long an object's storage can exist: which declarations produce static, thread, automatic and dynamic storage duration; dynamic storage is managed by the global operator new / operator delete, whose signatures and required contracts are also specified here."
updated: 2026-10-19
---

!!! tldr
    - Storage duration describes how long storage exists, not objects: an object's lifetime always falls within its storage duration, but can be much shorter.
    - Namespace-scope variables and `static` variables have static storage duration, `thread_local` variables thread storage duration, ordinary local variables and parameters automatic storage duration, and whatever comes from `new` dynamic storage duration.
    - Static and local variables with side effects cannot be removed by the compiler even if they appear unused, which is what makes RAII guards and registrars reliable.
    - A replaceable `operator new` that fails may only throw `std::bad_alloc`, never return a null pointer; a request for 0 bytes must also return a unique non-null pointer. Replacements that break these contracts cause UB.
    - Deallocation functions are either usual or placement forms; a *delete-expression* calls only usual deallocation functions. C++20 also has destroying `operator delete`, which takes over destruction as well.

## Four storage durations [basic.stc.general]

```cpp run title="four-durations.cpp" ok
int a;                       // static: namespace scope
thread_local int t;          // thread: one per thread

int f(int param) {           // param: automatic
    int local = param;       // automatic: block scope
    static int calls = 0;    // static: block-scope static
    int* p = new int(local); // *p: dynamic
    delete p;
    return ++calls;
}

int main() { return f(a + t) == 1 ? 0 : 1; }
```

¶1 The **storage duration** is a property of an object that defines the minimum potential lifetime of the storage containing it. It is determined by the construct used to create the object, and there are four kinds:

| Storage duration | Produced by | Storage lasts until |
|---|---|---|
| static | namespace-scope variables; variables first declared with `static` or `extern`; static data members | the end of the program |
| thread | `thread_local` variables | the end of the thread |
| automatic | block-scope variables (without `static`, `thread_local` or `extern`); function parameters | the block exits; for parameters, after their destruction |
| dynamic | *new-expressions*; implicitly created objects ([[intro.object]]) | it is deallocated |

Storage duration governs storage; lifetime ([[basic.life]]) governs objects. An object's lifetime always falls within its storage duration but can be much shorter. For example, an object placed in a static buffer with placement new can end its lifetime in the middle of the program while the storage remains throughout.

¶2 Static, thread and automatic storage durations belong to objects introduced by declarations and to temporary objects ([[class.temporary]]); dynamic storage duration belongs to objects created by *new-expressions* and to implicitly created objects. ¶3 References are classified the same way. ¶4 The storage duration of subobjects and reference members is that of their complete object: members of `new S` have dynamic storage duration, and members of a local variable `S s;` have automatic storage duration.

Note 1 reminds us that when the storage duration of a region of storage ends, pointers to it become **invalid pointer values** ([[basic.compound]]). Dereferencing one is UB, and even copying or comparing one has implementation-defined effects.

## Static storage duration [basic.stc.static]

¶1 A variable that does not have thread storage duration and that belongs to a namespace scope or is first declared with `static` or `extern` has **static storage duration**. The storage lasts for the duration of the program; initialization is described in [[basic.start.static]] and destruction in [[basic.start.term]].

Block-scope `static` variables also have static storage duration. Their storage exists from program load, usually in the `.bss` or `.data` section; what happens the first time control passes through the declaration is only initialization ([[stmt.dcl]]).

¶2 If a variable with static storage duration has initialization or a destructor with side effects, the implementation shall not eliminate it even if it appears to be unused. The only exception is copy elision as permitted by [[class.copy.elision]]. The registrar idiom relies on this:

```cpp run title="registrar.cpp" ok
#include <cstdio>

struct Registrar {
    Registrar() { std::puts("registered"); }   // initialization with side effects
};

static Registrar reg;   // never used, but must not be eliminated: always prints at startup

int main() {}
```

!!! warning "The linker is not bound by this rule"
    ¶2 constrains variables that are already part of the program. If `reg` is in an object file inside a static library (`.a`) none of whose symbols is referenced, the linker does not pull that object file into the program at all, which does not violate ¶2. This is a common reason why plugin registration code stops working once it is put in a static library.

## Thread storage duration [basic.stc.thread]

¶1 A variable declared with `thread_local` has **thread storage duration**; its storage lasts until the thread in which it is created ends. Each thread has a distinct object, and the name refers to the one associated with the current thread. ¶2 is a note: a variable with thread storage duration, if constructed, is destroyed at thread exit ([[basic.start.term]]).

```cpp run title="thread-local.cpp" ok
#include <cassert>
#include <thread>

thread_local int counter = 0;   // one per thread

void work() {
    for (int i = 0; i < 1000; ++i) ++counter;   // no data race: each uses its own
    assert(counter == 1000);
}

int main() {
    std::thread t1(work), t2(work);
    t1.join(); t2.join();
    return counter;   // the main thread's own counter: 0
}
```

A `thread_local int x;` at block scope implies `static` ([[dcl.stc]]) and is not recreated each time the block is entered.

## Automatic storage duration [basic.stc.auto]

¶1 Variables that belong to a block scope and are not explicitly declared `static`, `thread_local` or `extern` have **automatic storage duration**; their storage lasts until the block in which they are created exits. Function parameters also have automatic storage duration, and their storage ends immediately after the parameter is destroyed.

The sentence about parameters is carefully worded. Whether a parameter is destroyed when the function returns or at the end of the enclosing full-expression is implementation-defined ([[expr.call]]), so the end of its storage can only follow its destruction, not the function's return.

¶2 If a variable with automatic storage duration has initialization or a destructor with side effects, the implementation shall not destroy it before the end of its block, nor eliminate it as an optimization (except for copy elision). This is what makes RAII guards reliable:

```cpp run title="raii-guard.cpp" ok
#include <mutex>

std::mutex m;
int shared = 0;

void f() {
    std::lock_guard<std::mutex> g(m);   // g is never used, but must not be destroyed early
    ++shared;
}   // the lock is released here

int main() { f(); return shared == 1 ? 0 : 1; }
```

!!! pitfall "Temporaries are not variables"
    `std::lock_guard<std::mutex>{m};` has no name; it creates a temporary object that is destroyed at the end of the statement ([[class.temporary]]) and protects nothing on the next line. ¶2 protects only variables.

## Dynamic storage duration [basic.stc.dynamic]

### Allocation and deallocation functions [basic.stc.dynamic.general]

¶1 Objects can be created at run time with *new-expressions* ([[expr.new]]) and destroyed with *delete-expressions* ([[expr.delete]]). The implementation manages dynamic storage through the global **allocation functions** `operator new` and `operator new[]` and the global **deallocation functions** `operator delete` and `operator delete[]`. Note 1 points out that non-allocating forms such as `operator new(std::size_t, void*)` ([[new.delete.placement]]) neither allocate nor deallocate.

¶2 The standard library provides default definitions of these functions, some of which are **replaceable** ([[dcl.fct.def.replace]]): a program that defines a function with the same signature replaces the library version. The following functions are implicitly declared at global scope in each translation unit:

```cpp
void* operator new(std::size_t);
void* operator new(std::size_t, std::align_val_t);
void  operator delete(void*) noexcept;
void  operator delete(void*, std::size_t) noexcept;
void  operator delete(void*, std::align_val_t) noexcept;
void  operator delete(void*, std::size_t, std::align_val_t) noexcept;
// plus the corresponding operator new[] and operator delete[]
```

The implicit declarations introduce only these four function names, not `std`, `std::size_t` or `std::align_val_t` (note 2). So `new` and `delete` can be used without including any header:

```cpp run title="no-include-new.cpp" ok
int main() {
    int* p = new int(1);          // OK: no #include <new> needed
    void* q = operator new(16);   // OK: calls the allocation function directly
    operator delete(q);
    delete p;
    // std::size_t n = 0;         // error: std::size_t is not declared
}
```

The `nothrow` and placement versions are not implicitly declared and require `<new>`. Classes can also declare their own allocation and deallocation functions ([[class.free]]), which *new-expressions* look up in the class first.

¶3 If the behavior of an allocation or deallocation function does not satisfy the semantic constraints specified in the two sections below, the behavior is undefined. This is a requirement on replacements: if you replace the global `operator new`, you must honor the same contract.

### Allocation functions [basic.stc.dynamic.allocation]

#### Signature (¶1)

An allocation function that is not a class member must be at global scope and must not have internal linkage. The return type must be `void*`; the first parameter must be `std::size_t`, the number of bytes requested, and must not have a default argument. An allocation function can be a template, but its return type and first parameter must not depend on template parameters, and the template must have at least two parameters, so that it cannot capture an ordinary `new T`.

```cpp run title="alloc-sig.cpp" error
#include <cstddef>

namespace N { void* operator new(std::size_t); }   // error: not at global scope
static void* operator new(std::size_t, int);       // error: internal linkage
void* operator new(std::size_t = 0, double);       // error: the first parameter has a default argument
template<class T> void* operator new(T);           // error: only one parameter
```

#### On success (¶2)

On success, it returns the address of the start of a block of storage whose length is at least the size requested. The order, contiguity and initial values of storage allocated by successive calls are unspecified.

A replaceable allocation function returns a non-null pointer on success, distinct from any value previously returned, unless that value has since been passed to a replaceable deallocation function. This holds for 0-byte requests too: two `new char[0]` give two distinct non-null pointers. Footnote 18 explains that these rules are intentionally consistent with `malloc`, so that `operator new` can be implemented directly with `malloc`; the only difference is that C's `malloc(0)` may return a null pointer. Indirecting through a pointer returned for a zero-size request is UB.

```cpp run title="zero-size.cpp" ok
int main() {
    char* a = new char[0];   // non-null and unique
    char* b = new char[0];
    bool distinct = a != b;  // always true
    // *a = 'x';             // UB: access through a pointer from a zero-size allocation
    delete[] a;
    delete[] b;
    return distinct ? 0 : 1;
}
```

For the standard library's own versions ([[new.delete.single]], [[new.delete.array]]), the returned storage is also guaranteed not to overlap any other object accessible to the caller.

#### Alignment (¶3)

Except for the reserved placement allocation functions, the returned storage must be aligned as follows:

- ¶3.1 if there is a `std::align_val_t` parameter, to the alignment it specifies;
- ¶3.2 otherwise, if it is `operator new[]`, for any object type no larger than the requested size whose alignment does not exceed `__STDCPP_DEFAULT_NEW_ALIGNMENT__`;
- ¶3.3 otherwise, for any object type whose size is exactly the requested size and whose alignment does not exceed `__STDCPP_DEFAULT_NEW_ALIGNMENT__`.

An alignment greater than `__STDCPP_DEFAULT_NEW_ALIGNMENT__` is a new-extended alignment ([[basic.align]]) and requires the version taking `align_val_t`. The array version has a broader requirement because `new char[64]` is often used as a buffer holding several smaller objects. By ¶3.3, a 2-byte request needs only 2-byte alignment, though mainstream implementations simply give `__STDCPP_DEFAULT_NEW_ALIGNMENT__`.

#### On failure (¶4)

When allocation fails, the allocation function can call the currently installed new-handler ([[new.handler]]); a program-supplied version can obtain it with `std::get_new_handler`. A non-throwing allocation function (such as the `nothrow` version) indicates failure by returning a null pointer; any other allocation function **never returns a null pointer** and can only throw an exception of a type that a `std::bad_alloc` handler would catch.

So there is no need to check for null after an ordinary `new T`, and compilers delete such checks on this basis. [[expr.new]] requires checking the return value before initializing the object only when the allocation function does not throw.

#### When it is called (¶5)

The global allocation functions are called only in these cases: a *new-expression*; a direct call using function call syntax; allocating storage for a coroutine state ([[dcl.fct.def.coroutine]]); and indirect calls through standard library functions.

Note 2 lists objects that do not use the global allocation functions: objects with static storage duration, objects and references with thread storage duration, `std::type_info` objects, the `std::contracts::contract_violation` object on a contract violation {{c++26}}, and exception objects ([[except.throw]]). Exception objects are allocated separately by the implementation, for example by `__cxa_allocate_exception` in the Itanium ABI.

!!! note "Allocations can be omitted"
    [[expr.new]] allows an implementation to omit a *new-expression*'s call to a replaceable global allocation function and use storage it provides itself (for example on the stack), or to merge several allocations into one. So replacing `operator new` to count calls does not necessarily give the number of `new` occurrences in the source:

    ```cpp run title="alloc-elision.cpp" unspecified
    #include <cstdio>
    #include <cstdlib>
    #include <new>

    int count = 0;
    void* operator new(std::size_t n) {
        ++count;
        if (void* p = std::malloc(n ? n : 1)) return p;
        throw std::bad_alloc();
    }
    void operator delete(void* p) noexcept { std::free(p); }
    void operator delete(void* p, std::size_t) noexcept { std::free(p); }

    int main() {
        int* p = new int(42);
        int v = *p;
        delete p;
        std::printf("v=%d count=%d\n", v, count);   // Clang 23: 1 at -O0, 0 at -O2
    }
    ```

    This permission covers only *new-expressions*; a call written directly as `::operator new(n)` cannot be omitted. Clang provides `__builtin_operator_new` so that library code like `std::allocator` can get this optimization too; that is an implementation extension. During constant evaluation, calls to replaceable allocation functions are always omitted, which is what makes `new` usable in `constexpr`.

### Deallocation functions [basic.stc.dynamic.deallocation]

#### Signature (¶1–¶3)

¶1 A deallocation function that is not a class member must be at global scope and must not have internal linkage. ¶3 specifies that a deallocation function's return type must be `void` and it must not have a potentially-throwing exception specification (without one it is implicitly `noexcept`); the first parameter is `void*`, except for destroying delete (see below).

¶3 also defines **usual deallocation functions**: after the first parameter there are only, in order, an optional `std::destroying_delete_t`, an optional `std::size_t`, and an optional `std::align_val_t`. A deallocation function can be a template, with the same rules as allocation functions, but a template instance is never a usual deallocation function.

The distinction matters because a *delete-expression* calls only usual deallocation functions ([[expr.delete]]). Other forms of `operator delete` have one use only: when a constructor in a placement new throws, they pair with that placement `operator new` to release the storage just allocated.

#### Sized and aligned deallocation

`operator delete(void*, std::size_t)` is **sized deallocation** {{c++14}}. When a *delete-expression* knows the object's size, it passes it along, so the allocator need not record or look up the block size itself ([[N3778]]).

Footnote 19 points out a side effect: with a global `operator delete(void*, std::size_t)`, `void* operator new(std::size_t, std::size_t)` can no longer be used as a placement allocation function, because its matching placement delete has the same signature as the sized deallocation function. This was an incompatible change in C++14 ([[diff.cpp11.basic]]).

The versions taking `std::align_val_t` are **aligned deallocation** {{c++17}}, paired with allocations of new-extended alignment ([[P0035R4]]).

#### Destroying delete {{c++20}}

¶2 A deallocation function whose second parameter has type `std::destroying_delete_t` is a **destroying operator delete**. It must be a class member function whose first parameter is a pointer to that class; it must be a usual deallocation function; and note 1 explains that it cannot be used for array deletion.

An ordinary `delete p` first calls the destructor and then calls `operator delete` to release the storage. A destroying delete hands both steps to you: the compiler does not call the destructor, and passes the pointer straight to it.

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
    enum Kind { kCircle, kSquare } kind;
    void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; };
struct Square : Shape { double side; };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    // dispatch destruction and deallocation manually by kind; no virtual destructor needed
    if (p->kind == kCircle) {
        auto* c = static_cast<Circle*>(p);
        c->~Circle();
        ::operator delete(c, sizeof(Circle));
    } else {
        auto* s = static_cast<Square*>(p);
        s->~Square();
        ::operator delete(s, sizeof(Square));
    }
    std::puts("destroyed");
}

int main() {
    Shape* s = new Circle{{Shape::kCircle}, 1.0};
    delete s;   // does not call ~Shape(); calls Shape::operator delete directly
}
```

It suits two kinds of code: hand-rolled polymorphism without virtual destructors, such as LLVM's `Value` hierarchy; and variable-length objects allocated together with trailing data, which need the real size when freed. Destroying delete was introduced by [[P0722R3]].

#### Semantics (¶4–¶5)

¶4 The first argument passed to a deallocation function may be a null pointer; for the deallocation functions provided by the standard library, such a call has no effect, which is why `delete nullptr` is safe. ¶5 If the argument is not null, the standard library's deallocation functions deallocate the storage it points to; the storage duration of that storage ends, and all pointers to it become invalid pointer values.

## Replacing the global allocation functions

[[dcl.fct.def.replace]] and [[new.delete]] specify that a program may define replaceable global allocation or deallocation functions in one of its translation units. Replacements cannot be declared `inline` and must honor the contracts above:

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

static std::size_t live = 0;

void* operator new(std::size_t n) {
    if (n == 0) n = 1;                    // a 0-byte request must also return a unique non-null pointer
    for (;;) {
        if (void* p = std::malloc(n)) { ++live; return p; }
        std::new_handler h = std::get_new_handler();
        if (!h) throw std::bad_alloc();   // failure can only throw, never return null
        h();                              // let the new-handler try to free some memory
    }
}
void operator delete(void* p) noexcept {
    if (p) { --live; std::free(p); }
}
void operator delete(void* p, std::size_t) noexcept { operator delete(p); }

int main() {
    auto* v = new int[4];   // the default operator new[] calls operator new
    delete[] v;
    std::printf("live=%zu\n", live);
}
```

The library's default `operator new[]` and `nothrow` versions all call `operator new(std::size_t)` (directly or indirectly), and the default `operator delete[]` and sized versions call `operator delete(void*)` ([[new.delete]]). So replacing these two basic functions usually intercepts all non-aligned global allocations. The aligned versions are a separate set and must be replaced separately.

## Implementation view

!!! impl
    - The default `operator new` in libstdc++ and libc++ is `malloc` plus the loop calling the new-handler and throwing `bad_alloc`, in line with the intent of footnote 18. The aligned versions call `aligned_alloc` or `posix_memalign`, and `_aligned_malloc` on Windows.
    - Sized deallocation: GCC enables it by default since C++14; Clang required `-fsized-deallocation` for a long time, because it depends on the runtime library providing the corresponding symbols, and only later made it the default. Allocators like tcmalloc and jemalloc benefit noticeably from the size information.
    - Allocation elision: Clang aggressively eliminates paired `new`/`delete`; the counting example above prints `count=0` at `-O2`.
    - Thread storage duration: ELF platforms implement it with TLS sections (`.tdata`, `.tbss`) and `__tls_get_addr`. A `thread_local` with non-trivial construction or destruction needs a wrapper function that completes initialization on first use (the TLS wrapper of the Itanium ABI) and a registration mechanism that runs destructors at thread exit (`__cxa_thread_atexit`).

## History

!!! history
    - C++98: three storage durations, static, automatic and dynamic; global `operator new`/`delete` and their array, `nothrow` and placement forms.
    - C++11: added thread storage duration and `thread_local`.
    - C++14: sized deallocation ([[N3778]]); allocations may be omitted and merged ([[N3664]]).
    - C++17: aligned allocation and deallocation, `std::align_val_t`, `__STDCPP_DEFAULT_NEW_ALIGNMENT__` ([[P0035R4]]).
    - C++20: destroying `operator delete` ([[P0722R3]]); `new`/`delete` usable in `constexpr`; implicitly created objects classified as dynamic storage duration.
    - C++26: with contracts, note 2 added `std::contracts::contract_violation`.

## Common misconceptions

!!! pitfall "Allocation and deallocation can be mixed"
    `new` goes with `delete`, `new[]` with `delete[]`, `malloc` with `free`. Mixing them is outside the contracts above, and [[expr.delete]] makes it UB.

!!! pitfall "A replacement `operator new` may return a null pointer"
    A non-`noexcept` allocation function returning null violates ¶4 and is UB per ¶3. Compilers assume the result of `new` is non-null and may delete an `if (!p)` check you write afterward.

!!! pitfall "Storage for a local `static` variable is allocated on the first call"
    Its storage duration covers the whole run of the program. What happens the first time control passes through the declaration is only initialization; the storage exists from program load.

## Questions

!!! question "Question 1"
    Which of the allocation function declarations below are valid?

    ```cpp
    void* operator new(std::size_t, std::size_t);            // (a)
    template<class T> void* operator new(std::size_t, T);    // (b)
    void* operator new(std::size_t, int = 0);                // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

(a) The declaration itself is valid, but it cannot be used as a placement allocation function. When the constructor in `new (n) T` throws, a deallocation function with a matching signature is looked for, and the global sized deallocation function `operator delete(void*, std::size_t)` is found; it is a usual deallocation function, and [[expr.new]] makes the program ill-formed in that case (footnote 19).

(b) Valid: the template has two parameters, and neither the return type nor the first parameter depends on template parameters.

(c) Valid: only the first parameter may not have a default argument.
</details>

!!! question "Question 2"
    When does the storage of a function parameter end? Why doesn't the standard simply say it ends when the function returns?

<details markdown="1">
<summary>Answer</summary>

Per [basic.stc.auto] ¶1, a parameter's storage ends immediately after the parameter is destroyed. When the parameter is destroyed is specified by [[expr.call]]: whether at function return or at the end of the enclosing full-expression is implementation-defined. This has to do with calling conventions: in some ABIs the callee destroys parameters, in others the caller does. If the storage ended at function return, then in an ABI where the caller destroys parameters, the storage would no longer exist at destruction. So the end of the storage follows the destruction.
</details>

## Summary

| Storage duration | Source | Ends | Initial value if uninitialized |
|---|---|---|---|
| static | namespace-scope variables, `static`/`extern` variables, static data members | end of program | zero-initialized first |
| thread | `thread_local` | end of thread | zero-initialized first |
| automatic | block variables, parameters, most temporaries | block exit; for parameters, after destruction | erroneous value ([[basic.indet]]) |
| dynamic | *new-expressions*, implicit creation | deallocation | indeterminate value |

| Contract for allocation functions | Contract for deallocation functions |
|---|---|
| global scope, not internal linkage | global scope, not internal linkage |
| returns `void*`, first parameter `std::size_t` without a default argument | returns `void`, must not throw |
| success: non-null, unique, aligned | null pointer argument: no effect for library versions |
| failure: throw `bad_alloc`; `noexcept` versions return null | non-null argument: ends the storage duration |
| 0-byte requests are valid, but the result cannot be dereferenced | usual deallocation functions: `[destroying_delete_t] [size_t] [align_val_t]` |
