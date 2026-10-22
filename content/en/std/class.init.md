---
title: Initialization of class objects
summary: "The ways a class object can be initialized and which rule handles each; elements of an array of class objects are constructed in subscript order and destroyed in reverse."
updated: 2026-10-19
---

!!! tldr
    - A class object with no initializer is default-initialized, and one whose initializer is `()` is value-initialized; the details are all in [[dcl.init]]. `T x();` declares a function, not a value-initialized object.
    - `T x(args)` is direct-initialization, `T x = e` is copy-initialization, and `T x{...}` and `T x = {...}` are list-initialization. Copy-initialization doesn't consider `explicit` constructors; copy-list-initialization is ill-formed if it selects an `explicit` constructor.
    - The `=` in a declaration is not assignment, and `operator=` has nothing to do with initialization.
    - Elements of an array of class objects are constructed in subscript order and destroyed in reverse order; if constructing an element throws, the elements already constructed are destroyed in reverse order.
    - When a braced initializer has fewer initializers than the array has elements, the remaining elements are initialized from an empty list, which requires a default constructor.

[[class.init]] has six subclauses. This page covers the two most basic: [[class.init.general]] and [[class.expl.init]]. For how constructors initialize bases and members see [[class.base.init]], for inherited constructors see [[class.inhctor.init]], for the state of an object during construction and destruction see [[class.cdtor]], and for copy elision see [[class.copy.elision]].

## No initializer, or `()` ([class.init.general] ¶1–¶2)

```cpp run title="init-empty.cpp" ok
#include <cstdio>

struct Agg { int a; int b; };
struct User { int a; User() {} };
struct Defaulted { int a; Defaulted() = default; };

int main() {
    Agg* p1 = new Agg();              // value-initialization: zeroed
    User* p2 = new User();            // value-initialization: only calls User()
    Defaulted* p3 = new Defaulted();  // value-initialization: zeroed
    std::printf("%d %d %d\n", p1->a, p1->b, p3->a);  // 0 0 0
    // p2->a is not initialized, so it isn't read here
    delete p1; delete p2; delete p3;
}
```

¶1 When an object of class type (or array thereof) has no initializer, or its initializer is `()`, it is initialized as specified in [[dcl.init]]. The former is **default-initialization** ([[g:default-initialization]]): for a class type, the default constructor is selected and called. The latter is **value-initialization** ([[g:value-initialization]]): if the default constructor is not user-provided, the whole object is first zeroed and then default-initialized; otherwise the default constructor is simply called.

So in the example above, `User`'s default constructor is user-provided and `a` isn't zeroed. `Defaulted() = default;` is defaulted on its first declaration in the class, so it isn't user-provided ([[dcl.fct.def.default]]), and value-initialization still zeroes first.

| Form | Initialization |
|---|---|
| `T x;`, `new T` | Default-initialization |
| `T()`, `new T()`, *mem-initializer* `m()` | Value-initialization |
| `T x{};`, `T{}` | List-initialization; for a non-aggregate class with a default constructor this is value-initialization ([[dcl.init.list]]) |

The `()` form can't be used in a variable declaration: `T x();` declares a function returning `T` ([[dcl.ambig.res]]). To value-initialize a local variable, write `T x{};` or `T x = T();`.

¶2 is only a pointer: class objects can be explicitly initialized; see [[class.expl.init]] and [[class.base.init]].

## Parentheses and `=` ([class.expl.init] ¶1)

```cpp run title="complex.cpp" ok
struct complex {
    complex() {}
    complex(double) {}
    complex(double, double) {}
};
complex sqrt(complex, complex) { return {}; }

int main() {
    complex a(1);              // complex(double)
    complex b = a;             // copy constructor
    complex c = complex(1, 2); // c is the result object of this prvalue
    complex d = sqrt(b, c);    // d is the result object of the function call
    complex e;                 // complex()
    complex f = 3;             // complex(double)
    complex g = {1, 2};        // complex(double, double)
    (void)d; (void)e; (void)f; (void)g;
}
```

¶1 A class object can be initialized with a parenthesized *expression-list*, whose expressions are the arguments to a constructor; this is **direct-initialization** ([[g:direct-initialization]]). It can also be initialized with the `= expression` form, which is **copy-initialization** ([[g:copy-initialization]]). The precise semantics of both are in [[dcl.init#15.6]]. For a target of class type:

- if the initializer is a prvalue of the same type, it initializes the target directly, without going through a copy or move constructor ([[dcl.init#15.6.1]]);
- for direct-initialization, or copy-initialization where the source type is the same class or a derived class, overload resolution is performed among the constructors;
- for any other copy-initialization, a user-defined conversion from the source type to the target type is sought ([[over.match.copy]]), and `explicit` constructors don't take part.

Before C++17, the `c` and `d` lines were described as: construct a temporary first, then copy it into `c` or `d`; the copy could be elided, but the copy constructor had to be accessible. Since C++17, a prvalue no longer becomes a temporary first; it is just a way of initializing some result object, and `c` and `d` are themselves the result objects, with no copy step ([[basic.lval#5]]).

### `explicit` constructors

```cpp title="explicit.cpp" error
struct S {
    explicit S(int) {}
};

S a(1);       // OK: direct-initialization
S b{1};       // OK: direct-list-initialization
S c = 1;      // error: explicit constructors not considered
S d = {1};    // error: an explicit constructor was selected
S e = S(1);   // OK: prvalue of the same type
```

`c` and `d` fail in different ways. The copy-initialization of `c` doesn't put `explicit` constructors in the candidate set at all. The copy-list-initialization of `d` does put them in, but if overload resolution selects one, the program is ill-formed ([[over.match.list]]). When there are other non-`explicit` candidates, this difference can change the outcome; see the question at the end.

### The `=` in a declaration is not assignment

```cpp run title="not-assignment.cpp" ok
struct S {
    S(int) {}
    S& operator=(int) = delete;
};

int main() {
    S s = 42;     // OK: copy-initialization, calls S(int)
    // s = 43;    // this is assignment: error
    (void)s;
}
```

Note 1: overloading the assignment operator ([[over.assign]]) has no effect on initialization. The `=` in `T x = e;` is part of the declaration syntax.

## Braces ([class.expl.init] ¶2)

¶2 A class object can also be initialized with a braced initializer list, in which case list-initialization applies ([[dcl.init.list]]). For class types it falls roughly into three cases: an aggregate class gets aggregate initialization ([[dcl.init.aggr]]), copy-initializing each member in turn; a class with an `std::initializer_list` constructor considers that first; otherwise the elements in the braces are used as constructor arguments for overload resolution. All three forbid narrowing conversions.

The array from Example 2 in the standard, with output added:

```cpp run title="array-braced.cpp" ok
#include <cstdio>

struct complex {
    complex()               { std::printf("() "); }
    complex(double)         { std::printf("(d) "); }
    complex(double, double) { std::printf("(d,d) "); }
};

int main() {
    complex v[6] = {1, complex(1, 2), complex(), 2};
    std::puts("");   // (d) (d,d) () (d) () ()
    (void)v;
}
```

`v[0]` and `v[3]` are copy-initialized via `complex(double)`. The initializers for `v[1]` and `v[2]` are prvalues of the same type, which initialize the elements directly. `v[4]` and `v[5]` have no corresponding initializer and are initialized from an empty list per [[dcl.init.aggr]], that is, by calling `complex()`.

```cpp run title="aggr-class-member.cpp" ok
struct complex { complex(double) {} };

struct X {
    int i;
    float f;
    complex c;
} x = {99, 88.8, 77.7};   // c is initialized by complex(double)

int main() { (void)x; }
```

`88.8` is a `double`, and converting it to `float` isn't narrowing here: the source is a constant expression and the converted value is within the range of `float` ([[dcl.init.list]]). Note 2 points out that inner braces can be elided in an aggregate's initializer list, even when the member is of a class type with user-defined conversions ([[dcl.init.aggr]]).

## Classes without a default constructor ([class.expl.init] ¶3–¶4)

```cpp title="no-default-ctor.cpp" error
struct NoDef { NoDef(int) {} };

NoDef a(1);              // OK
NoDef b;                 // error: no default constructor
NoDef arr1[2] = {1};     // error: arr1[1] needs default construction
NoDef arr2[2] = {1, 2};  // OK
```

¶3 is a note: if `T` has no default constructor, a declaration of a `T` object (or array) without an initializer is ill-formed. This follows directly from the default-initialization rules.

`arr1` is a common trap. When there are fewer initializers than elements, the remaining elements aren't left uninitialized; they are initialized from an empty list, which for `NoDef` requires a default constructor. Only `E arr[3];`, with no initializer at all, default-initializes each element.

¶4 is also a note, pointing to the order of initialization of objects with static and thread storage duration: see [[basic.start.dynamic]] and [[stmt.dcl]].

## Construction order of array elements ([class.init.general] ¶3)

```cpp run title="array-order.cpp" ok
#include <cstdio>

struct E {
    int id;
    E(int i) : id(i) { std::printf("E(%d) ", id); }
    ~E() { std::printf("~E(%d) ", id); }
};

int main() {
    E arr[3] = {1, 2, 3};   // E(1) E(2) E(3)
    std::puts("");
}                           // ~E(3) ~E(2) ~E(1)
```

¶3 When an array of class objects is initialized and the elements are initialized by constructors, the constructors are called for each element in subscript order (see also [[dcl.array]]). Note 1 adds that the elements are destroyed in the reverse order of their construction.

With the order fixed, constructor side effects (printing, allocating resources, registering in a global table) are consistent across implementations. It also gives exception handling a definite outcome: when construction of the *k*-th element throws, the first *k* − 1 elements have been fully constructed and are destroyed in reverse order ([[except.ctor#3]]).

```cpp run title="array-throw.cpp" ok
#include <cstdio>
#include <stdexcept>

struct E {
    int id;
    E(int i) : id(i) {
        if (i == 3) throw std::runtime_error("boom");
        std::printf("E(%d) ", id);
    }
    ~E() { std::printf("~E(%d) ", id); }
};

int main() {
    try {
        E arr[4] = {1, 2, 3, 4};
    } catch (const std::exception&) {
        std::puts("caught");   // preceded by E(1) E(2) ~E(2) ~E(1)
    }
}
```

`new E[4]{1, 2, 3, 4}` behaves the same: the constructed elements are destroyed in reverse order, and then the matching deallocation function frees the storage ([[expr.new]]).

## Questions

!!! question "Question"
    Which constructor of `S` does each of the three lines call? Which lines are ill-formed?

    ```cpp
    struct S {
        S(int);
        explicit S(long);
        S(const S&);
    };
    S a = 1L;
    S b(1L);
    S c = {1L};
    ```

<details markdown="1">
<summary>Answer</summary>

`S a = 1L;` is copy-initialization; the source type `long` differs from `S`, so only non-`explicit` converting constructors are considered, and `S(int)` is used (an integral conversion from `long` to `int`). Valid.

`S b(1L);` is direct-initialization; `S(long)` is an exact match and beats `S(int)`. Valid.

`S c = {1L};` is copy-list-initialization; `explicit S(long)` is in the candidate set and is an exact match, so it is selected and the program is ill-formed ([[over.match.list]]). `S(int)` would have been usable (`1L` is a constant, so converting it to `int` isn't narrowing), but that doesn't change the result. Clang 23 reports `chosen constructor is explicit in copy-initialization`.
</details>
