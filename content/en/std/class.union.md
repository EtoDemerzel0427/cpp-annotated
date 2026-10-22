---
title: Unions
summary: "A union has at most one active member at any time; when assigning to a member switches the active member, and how to manage lifetimes by hand for members like std::string; the common initial sequence exception, anonymous unions and variant members."
updated: 2026-10-19
---

!!! tldr
    - The members of a union share the same storage, and at any time at most one member is within its lifetime; that member is called the active member. Reading an inactive member is undefined behavior, so type punning by writing a `float` and reading a `uint32_t` doesn't work in C++; use `std::bit_cast` instead.
    - Assigning to a simple member such as an `int` with built-in assignment first makes it the active member and then assigns. When the member is a type with a non-trivial constructor such as `std::string`, you have to destroy the old member by hand and then construct the new one with placement new or `std::construct_at`.
    - When a member has non-trivial copy or move operations, the union's corresponding functions are deleted. Since C++26, a union's default constructor and destructor are no longer deleted because of non-trivial members, but Clang 23 doesn't implement this yet.
    - In a standard-layout union, the leading members that several struct members have in common (the common initial sequence) can be read through any of those structs.
    - The member names of an anonymous union belong directly to the enclosing scope; the members of unions and anonymous unions are together called variant members, and at most one of them can have a default member initializer.

## The active member (¶1–¶2)

```cpp run title="inactive-read.cpp" ub
union U { int i; float f; };

int main() {
    U u{.i = 1};     // active member: i
    float x = u.f;   // UB: u.f is not within its lifetime
    return x > 0;
}
```

¶1 A union is a class defined with the `union` keyword. It can have member functions, constructors, destructors and access specifiers, and it is treated like a `struct` in overload resolution and template deduction, except that its members are public by default. This page covers how it differs from ordinary classes.

¶2 The non-static data members of a union share the same storage. A member is **active** if its name refers to an object that is within its lifetime ([[basic.life]]). At most one member is active at a time, which means a union holds the value of at most one member. It may also hold none, for example after `U u;` initializes no member.

!!! std
    In a union, a non-static data member is *active* if its name refers to an object whose lifetime has begun and has not ended.

Being active isn't a hidden flag inside the union; it is determined entirely by lifetime. Switching the active member means ending the old member's lifetime and starting the new member's. Reading an inactive member means performing an lvalue-to-rvalue conversion on an object that is not within its lifetime, which [[basic.life#8]] says is undefined behavior.

### Type punning doesn't work in C++

C allows writing one member and reading another, with the effect of reinterpreting the same bytes as the new type. C++ didn't adopt that rule: each member is a separate object, and reading an object that isn't within its lifetime has no defined meaning; besides, a member may be a class type with invariants, and reinterpreting bytes as such a type isn't safe.

```cpp run title="type-punning.cpp" ub
#include <cstdint>

union Pun { float f; std::uint32_t u; };

std::uint32_t bits_bad(float x) {
    Pun p;
    p.f = x;
    return p.u;      // UB: the active member is f
}

int main() { return bits_bad(1.0f) == 0x3f800000 ? 0 : 1; }
```

GCC explicitly supports this as an extension, and Clang behaves the same way, so in practice it works; but both reject it in constant evaluation, and it isn't portable C++. The portable way is C++20's `std::bit_cast`, or `std::memcpy`:

```cpp run title="bit-cast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t bits(float x) {
    return std::bit_cast<std::uint32_t>(x);
}
static_assert(bits(1.0f) == 0x3f800000);   // works at compile time too

int main() { }
```

## Switching the active member by assignment (¶5)

Given `union U { int i; float f; } u{.i = 1};`, is writing `u.f = 2.0f;` valid? By [[basic.life]], `u.f` isn't within its lifetime at that point, so assigning to it modifies an object outside its lifetime, which ought to be UB. But C and C++ code has always been written this way. ¶5 provides the basis for it: when certain conditions are met, the assignment first creates an `f` in that storage and then assigns to it.

```cpp run title="assign-switch.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = static_cast<float>(u.i);   // reads i, then creates f, then assigns
    return u.f == 1.0f ? 0 : 1;      // OK: f is the active member
}
```

### The rule

¶5 For an assignment `E1 = E2` that uses the built-in assignment operator or a trivial assignment operator, the standard picks out a set of union member accesses from the left operand `E1`, written S(E1). For each element X of it, if modifying X would be UB under [[basic.life]] (X is not within its lifetime), then:

- an object of X's type is implicitly created in the storage X names;
- no initialization is performed;
- its lifetime begins after both operands are evaluated and before the assignment.

Note 4 adds that this ends the lifetime of the union's previously active member. The rule also covers anonymous union members that have elements of S(E1) as direct subobjects (recursively outward).

S(E) is defined recursively:

- ¶5.1 If `E` has the form `A.B`: S(E) contains all elements of S(A). In addition, if `B` is a union member whose type is a non-class non-array type, a class type with a trivial, non-deleted default constructor, or an array of such types, `A.B` itself is added.
- ¶5.2 If `E` has the form `A[B]` and is a built-in subscript: if `A` is an array, S(E) = S(A); if `B` is an array (the `i[arr]` form), S(E) = S(B); otherwise it is empty. When `A` is a pointer, the chain stops here.
- ¶5.3 Any other form: S(E) is empty.

Each of these conditions has a reason:

1. Only trivial, non-deleted default constructors are accepted, because the new object starts its lifetime without initialization. An object that appears out of nowhere like this doesn't break the type's invariants only if doing nothing is already a valid default initialization of the type. A type like `std::string` can't be conjured out of nothing.
2. Only built-in or trivial assignment is accepted. A user-defined `operator=` is an ordinary member function call, and its `this` must point to an object within its lifetime; trivial assignment just copies bytes, which is fine on an uninitialized new object.
3. The new object's lifetime begins only after the right operand is evaluated, so reading the old member while writing the new one, as in `u.f = u.i;`, is valid: `u.i` is still active when it is read.

### Nesting and arrays

Example 2 in the standard shows how S(E) works its way outward along member accesses:

```cpp run title="nested-union-assign.cpp" ok
union A { int x; int y[4]; };
struct B { A a; };
union C { B b; int k; };

constexpr int f() {
    C c;                  // no member's lifetime begins
    c.b.a.y[3] = 4;       // OK: creates c.b and c.b.a.y
    return c.b.a.y[3];    // OK
}
static_assert(f() == 4);  // holds in constant evaluation too

int main() { return f() == 4 ? 0 : 1; }
```

Computing S(`c.b.a.y[3]`) step by step:

1. It has the form `A[B]` and `c.b.a.y` is an array, so the result equals S(`c.b.a.y`).
2. `c.b.a.y` has the form `A.B`; `y` is a member of union `A` with type array of `int`, so it is added.
3. In `c.b.a`, `a` is a member of struct `B`, not a union member, so it isn't added.
4. In `c.b`, `b` is a member of union `C`, and `B` has a trivial default constructor, so it is added.

The result is {`c.b`, `c.b.a.y`}; both objects are implicitly created and become the active members of their respective unions.

### When the rule doesn't apply

The second half of Example 2:

```cpp run title="const-member-no-switch.cpp" ub
struct X { const int a; int b; };
union Y { X x; int k; };

int main() {
    Y y = { { 1, 2 } };   // OK: y.x is the active member
    int n = y.x.a;
    y.k = 4;              // OK: ends y.x; y.k becomes the active member
    y.x.b = n;            // UB: y.x is not recreated
    return y.x.b;
}
```

`X` has a `const` member without an initializer, so its default constructor is deleted ([[class.default.ctor#2]]) and `y.x` doesn't satisfy ¶5.1; `b` is a struct member, not a union member. So S(`y.x.b`) is empty, no object is created, and `y.x.b = n` modifies an object outside its lifetime.

!!! impl "Clang misses this UB in constant evaluation"
    Rewrite the code above as a `constexpr` function and call it in a `static_assert`, and Clang 23 accepts it without error. By the standard this is UB, and constant evaluation must reject it ([[expr.const.core]]). For members whose default constructor is non-trivial, Clang does correctly report an assignment to an inactive member.

A user-defined assignment operator doesn't trigger the switch either:

```cpp run title="user-assign-no-switch.cpp" ub
struct P {
    int v;
    P& operator=(int x) { v = x; return *this; }   // not a trivial assignment
};
union U { int i; P p; };

int main() {
    U u{.i = 0};
    u.p = 5;     // UB: u.p is not within its lifetime when P::operator= is called
    return u.p.v;
}
```

Also, `std::start_lifetime(r)` in [[obj.lifetime]] can explicitly start the lifetime of a union member, making it the active member without initializing anything. It requires the member type to be an implicit-lifetime aggregate type.

## Unions with non-trivial members (¶4 note 3, ¶6)

Since C++11, a union member can be a type with non-trivial special member functions, like `std::string`. A union doesn't know which member is active, so the compiler can't generate correct copy, move and destruction for it. ¶4 Note 3 describes how the standard handles this: if any member has a non-trivial copy constructor, move constructor, copy assignment or move assignment, the union's corresponding function must be user-provided, or it is defined as deleted ([[class.copy.ctor]], [[class.copy.assign]]).

¶6 Note 5 points out that when ¶5 doesn't apply, the active member can only be switched with placement new (or the equivalent `std::construct_at`). Example 3 shows the approach: destroy the old member first, then construct the new one:

```cpp
u.m.~M();
new (&u.n) N;
```

Here is a complete tagged union, equivalent to a simplified `std::variant`:

```cpp run title="tagged-union.cpp" ok
#include <memory>
#include <string>
#include <utility>

class IntOrString {
    enum class Kind { Int, Str } kind_ = Kind::Int;
    union { int i_ = 0; std::string s_; };   // i_ active by default

    void destroy() {
        if (kind_ == Kind::Str) std::destroy_at(&s_);
    }

public:
    IntOrString() {}                // must be user-provided
    ~IntOrString() { destroy(); }   // destroys only the active member
    IntOrString(const IntOrString&) = delete;
    IntOrString& operator=(const IntOrString&) = delete;

    void set(int v) {
        destroy();
        i_ = v;                     // ¶5: an int can be assigned directly
        kind_ = Kind::Int;
    }
    void set(std::string v) {
        if (kind_ == Kind::Str) {   // already a string: ordinary assignment
            s_ = std::move(v);
            return;
        }
        std::construct_at(&s_, std::move(v));   // ¶6: the only way
        kind_ = Kind::Str;
    }
    const std::string* str() const {
        return kind_ == Kind::Str ? &s_ : nullptr;
    }
};

int main() {
    IntOrString x;
    x.set("hello, union");
    x.set(42);
    x.set("again");
    return x.str() ? 0 : 1;
}
```

Some key points:

- `s_ = std::move(v)` can only be used when `s_` is already active. `std::string::operator=` is user-provided and doesn't trigger ¶5.
- The destructor relies on `kind_` to know which member to destroy; the union itself doesn't record this.
- `kind_` is changed only after `construct_at` succeeds. If the construction throws, `kind_` is still `Int` and the destructor won't try to destroy a nonexistent `s_`; though in that case the union actually has no active member. `std::variant`'s `valueless_by_exception` state exists for this situation.

### C++26 trivial unions {{c++26}}

The example in note 3 is `union U { int i; float f; std::string s; };`. Its copy and move operations are all deleted; but under the current draft its default constructor and destructor are trivial, even though `std::string`'s corresponding functions are not.

It wasn't so in C++23 and earlier: `U`'s default constructor and destructor were also deleted, `U u;` was simply ill-formed, and you had to write `U() {}` and `~U() {}` by hand. [[P3074R7]] changed two places:

- [[class.default.ctor#3]]: when deciding whether the default constructor is trivial, unions no longer look at their members' types (¶3.4). A union's default constructor doesn't construct any member in the first place.
- [[class.dtor#7]]: a union's defaulted destructor is deleted in only two cases. One is that the constructor selected for default initialization is deleted or non-trivial (¶7.2.1); the other is that a variant member with a default member initializer has a non-trivial destructor (¶7.2.2). If default construction would make some member active, a destructor that does nothing could miss it, so it is deleted; when default construction does nothing, a destructor that does nothing is consistent with it.

The motivation was types like `std::inplace_vector<T, N>`, which have storage first and construct elements later. They used to have to write `union { T storage[N]; }` with hand-written empty constructors and destructors, and user-provided constructors and destructors make the whole type non-trivial and harder to use in constant evaluation.

```cpp run title="trivial-union.cpp"
#include <memory>
#include <string>
#include <type_traits>

union U { int i; std::string s; };

// C++26: default construction and destruction are both trivial
static_assert(std::is_trivially_default_constructible_v<U>);
static_assert(std::is_trivially_destructible_v<U>);
static_assert(!std::is_copy_constructible_v<U>);   // copying is still deleted

int main() {
    U u;                               // no active member
    std::construct_at(&u.s, "hello");  // s becomes the active member
    std::destroy_at(&u.s);             // must be ended by hand, or it leaks
}
```

This code is well-formed under C++26. Clang 23 doesn't implement [[P3074R7]] yet: the first two `static_assert`s fail and `U u;` is reported as calling a deleted default constructor, so no verdict is marked here. Until compilers support it, the portable way is to write the constructor and destructor by hand, as `IntOrString` above does.

!!! lawyer "Trivial members with default member initializers"
    By [[class.default.ctor#3]] ¶3.2, the default constructor is not trivial when a member has a default member initializer; and ¶7.2.1 says a union's destructor is deleted when default initialization selects a non-trivial constructor. Read literally, the destructor of `union X { int i = 0; float f; };` would also be deleted, even though all its members are trivial. That would break a lot of existing code and is probably not intended; watch for later revisions of the draft when reading this part.

## Common initial sequence (¶2 note 1)

¶2 Note 1 mentions a guarantee made to make unions easier to use; the formal rule is in [[class.mem.general#30]]:

```cpp run title="common-initial-sequence.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
    U u = { { 1, 2 } };   // the active member is t1
    return u.t2.c;        // OK: as if reading u.t1.a
    // return (int)u.t2.d; // UB: d is not in the common initial sequence
}

int main() { return f() == 1 ? 0 : 1; }
```

The **common initial sequence** of two standard-layout structs is the longest prefix, starting from the first member, in which corresponding members have layout-compatible types (see [[class.mem.general#27]] for the exact conditions, which also require the same alignment, bit-field widths and so on). In a standard-layout union whose active member is struct `T1`, the members in the common initial sequence can be read through another struct member `T2`, with the same effect as reading the corresponding member of `T1`.

This rule preserves a common C idiom for tagged unions: every member struct starts with the same tag field, and the tag can be read first no matter which one is currently active.

```cpp run title="tagged-cis.cpp" ok
enum Kind { K_INT, K_STR };
struct Any  { Kind kind; };
struct IntV { Kind kind; int value; };
struct StrV { Kind kind; const char* value; };
union Value { Any any; IntV i; StrV s; };

int get(const Value& v) {
    switch (v.any.kind) {     // valid whether i or s is active
    case K_INT: return v.i.value;
    case K_STR: return v.s.value[0];
    }
    return -1;
}

int main() {
    Value v{.i = {K_INT, 42}};
    return get(v) == 42 ? 0 : 1;
}
```

This exception allows only reading, not writing, and applies only to struct members. The `int` and `float` in `union { int i; float f; }` are not structs, so there is no common initial sequence to speak of.

!!! impl "Clang doesn't support this exception in constant evaluation"
    Make `f` above `constexpr` and call it in a constant expression, and Clang 23 reports a read of the inactive member `t2`. By the standard, this read is as if it named the corresponding member of `t1`, and isn't the read of an inactive member that [[expr.const.core]] forbids. This is an implementation limitation.

## Layout and restrictions (¶3–¶4)

¶3 A union is large enough to hold its largest member, and each member is allocated as if it were the sole member of a non-union class. Note 2 points out that a union object and each of its members are **pointer-interconvertible** ([[basic.compound]]): a pointer to one of them can be turned directly into a pointer to another with `reinterpret_cast`, or with `static_cast` via `void*`. So all members have the same address, equal to the union's address.

```cpp run title="union-address.cpp" ok
#include <cassert>

union U { char c; int i; double d; };
static_assert(sizeof(U) >= sizeof(double));
static_assert(alignof(U) >= alignof(double));

int main() {
    U u{.i = 7};
    assert((void*)&u.c == (void*)&u.d);
    int* p = reinterpret_cast<int*>(&u);   // points to the active member u.i
    assert(*p == 7);
}
```

The standard doesn't say `sizeof(U)` is exactly the size of the largest member; there may be padding at the end. In the mainstream ABIs it equals the size of the largest member rounded up to the strictest alignment.

¶4 A union can have member functions, including constructors and destructors, but there are four restrictions:

| Rule | Reason |
|---|---|
| No virtual functions | A union can't be derived from, so virtual functions are useless; a vtable pointer would also compete with the members for the first address |
| No base classes | A base class subobject always exists, which conflicts with the model of at most one active member |
| Can't be used as a base class | Same as above |
| No members of reference type | A reference is not an object and has no storage that could be switched |

```cpp title="union-restrictions.cpp" error
struct B {};
union U1 : B { int i; };          // error: a union can't have base classes
union U2 { int i; };
struct D : U2 {};                 // error: a union can't be used as a base class
union U3 { virtual void f(); };   // error: a union can't have virtual functions
union U4 { int& r; };             // error: member of reference type
```

## Constant evaluation and copying

The rules for unions in constant evaluation are in [[expr.const.core]]:

- Reading an inactive member (performing an lvalue-to-rvalue conversion on it) is not a core constant expression (¶2.11), so constant evaluation must detect this UB.
- Since C++20 ([[P1330R0]]), the active member can be switched in constant evaluation by an assignment under ¶5.
- When a union is trivially copied or moved, constant evaluation treats it as copying the active member (¶7).

```cpp run title="constexpr-union.cpp" ok
constexpr int ok() {
    union W { int a; float b; };
    W w{.a = 1};
    w.b = 2.0f;          // allowed in constant evaluation since C++20
    return (int)w.b;
}
static_assert(ok() == 2);

constexpr int bad() {
    union W { int a; float b; };
    W w{.a = 1};
    return (int)w.b;     // reads an inactive member
}
// static_assert(bad() == 0);   // error: not a constant expression

int main() { }
```

These rules are what allow `std::optional` and `std::variant` to be used in `constexpr` code.

When a union is copied at run time, the implicitly-defined copy or move constructor (when it exists and isn't deleted) copies the object representation and, for each object in the source, creates a corresponding object in the target ([[class.copy.ctor#16]]). So after `U v = u;`, `v` has the same active member as `u`.

## Anonymous unions [class.union.anon]

```cpp run title="anon-union.cpp" ok
#include <cstring>

int main() {
    union { int a; const char* p; };   // anonymous union
    a = 1;                             // used like an ordinary variable
    p = "Jennifer";                    // p becomes the active member
    return std::strlen(p) == 8 ? 0 : 1;
}
```

¶1 A declaration of the form `union { members } ;` is an **anonymous union**. It defines an unnamed type and an unnamed object of that type: if the object is a non-static data member it is called an anonymous union member, otherwise an anonymous union variable. The type can have no other objects. The names of an anonymous union's members are bound in the scope where the union is declared, so they are used directly like ordinary variables (or members of the enclosing class), except that they share an address.

The declarations in an anonymous union can only be public non-static data members, empty declarations or `static_assert`. It can't declare functions or nested types, including lambda closure types and nested anonymous unions. The reason is that an anonymous union has no name, so there is no way to write `Anon::f` outside it; it is just a group of variables sharing storage.

```cpp title="anon-union-restrictions.cpp" error
struct S {
    union { int a; float b; };              // OK
    union { int c; private: int d; };       // error: must be public
    union { int e; void f(); };             // error: can't declare functions
    union { int g; struct N {} n; };        // error: can't declare nested types
    union { int h; static_assert(true); };  // OK
};
```

¶2 The rules for storage class specifiers:

| Where | Rule |
|---|---|
| A namespace with external linkage (including the global namespace) | Must be `static` |
| Block scope | Only specifiers allowed for block variables, such as `static` and `thread_local` |
| Class scope | No storage class specifier |

A global anonymous union variable has no name, so no other translation unit could refer to it. Requiring `static` gives it internal linkage, so translation units don't need to agree on it. An unnamed namespace has no external linkage itself, so anonymous unions in it don't need `static`.

```cpp title="anon-union-storage.cpp" error
union { int ga; };                  // error: must be static
static union { int sa; };           // OK
namespace { union { int na; }; }    // OK: unnamed namespace

void f() {
    static union { int s1; };       // OK
    thread_local union { int s2; }; // OK
}

struct C {
    static union { int x; };        // error: not allowed at class scope
};
```

¶3 Note 1 points out that when an object, pointer or reference is declared after `union { … }`, it is not an anonymous union, and the members can only be accessed through the object:

```cpp title="not-anonymous.cpp" error
void f() {
    union { int aa; char* p; } obj, *ptr = &obj;
    aa = 1;           // error: aa is not in this scope
    ptr->aa = 1;      // OK
}
```

Note 2 refers to [[dcl.init.aggr]]: a union with no user-declared constructors is an aggregate; brace initialization initializes the first member by default, and a designated initializer such as `{.f = 1.0f}` can select another member.

## Union-like classes and variant members (¶4)

```cpp
struct Tagged {
    int tag;                      // ordinary member
    union { int i; double d; };   // i and d are variant members of Tagged
};                                // Tagged is a union-like class
```

¶4 A **union-like class** is a union, or a class that has an anonymous union as a direct member. Its **variant members** are the union's own non-static data members (other than anonymous unions) and the non-static data members of the anonymous unions that are its members. In the example above, `i` and `d` are variant members and `tag` is not.

This concept is used wherever rules need to distinguish members that always exist from members that may not be active. For example, variant members are handled separately when deciding whether the default constructor and destructor are deleted ([[class.default.ctor#2]], [[class.dtor#7]]); a class's destructor doesn't destroy variant members, since they may not be active at all ([[class.dtor]]); and a constructor's *mem-initializer*s can initialize at most one variant member of a union ([[class.base.init]]).

¶4 ends by saying that at most one variant member of a union can have a default member initializer, because default construction can make only one member active. Members of anonymous unions count toward the enclosing union:

```cpp title="one-dmi.cpp" error
union U {
    int x = 0;
    union {
        int k;
    };
    union {
        int z;
        int y = 1;      // error: U's second variant member with an initializer
    };
};
```

For a union-like class that isn't a union, like `Tagged`, each anonymous union is a separate union, and each may have at most one initializer.

## Implementation view

!!! impl
    - Under the Itanium C++ ABI, how a union is passed by value depends on whether it is trivial for the purposes of calls (trivial, non-deleted copy constructor and destructor).
    - GCC's documentation explicitly allows reinterpreting bytes by reading an inactive member directly through the union type, but not when the access goes through a pointer. This is an implementation guarantee, not a C++ guarantee.
    - `std::variant` is implemented as a recursive union in libstdc++, libc++ and the MSVC STL: each level contains one alternative and a union of the remaining types, with an index on the outside. `valueless_by_exception` corresponds to the state with no active member.

## History

!!! history
    - C++98/03: union members couldn't have non-trivial constructors, destructors or copy assignment, so `std::string` couldn't go in.
    - C++11: unrestricted unions allow non-trivial members, with the corresponding special member functions deleted and written by the programmer; default member initializers were introduced at the same time.
    - C++17: the object model was restated in terms of lifetime, and ¶5's switch-by-assignment rule was added with [[P0137R1]], giving a basis to long-standing practice.
    - C++20: the active member can be switched in constant evaluation ([[P1330R0]]); designated initializers make `U{.f = 1}` the standard way to choose a member.
    - C++26: trivial unions ([[P3074R7]]); a union's default constructor and destructor are no longer deleted because of non-trivial members.

## Common misconceptions

!!! pitfall "Writing A and reading B reinterprets the bytes as the new type"
    In C++ this is UB; GCC and Clang merely support it as an extension. Use `std::bit_cast`.

!!! pitfall "Assigning to a member always switches the active member"
    Only with built-in or trivial assignment, and only when the target type has a trivial, non-deleted default constructor. When `s` isn't active, `u.s = "x"` (`std::string`) is UB. The chain also stops at pointers: when the object `p` points to is itself not within its lifetime, `p->m = 1` doesn't create it.

!!! pitfall "A union destroys its active member"
    A union doesn't know which member is active, so it destroys no members. A union with non-trivial members must be destroyed explicitly by the surrounding code; conversely, destroying an inactive member (`u.s.~basic_string()`) is also UB ([[basic.life#7]]).

## Questions

!!! question "Question 1"
    Given `struct S { int a, b; }; union U { int i; S s; } u{.i = 1};`, which member is active after `u.s.b = 2;`? Can `u.s.b` be read? Can you count on `u.s.a == 1`?

<details markdown="1">
<summary>Answer</summary>

`b` is a struct member and isn't added to S; `s` is a union member and `S` has a trivial default constructor, so it is added. So `u.s` is implicitly created and becomes the active member, and the lifetime of `u.i` ends. Reading `u.s.b` gives 2.

`u.s.a` is within its lifetime, but the new object `u.s` hasn't been initialized at all. The standard doesn't say its value equals the old value of `u.i`; even though they occupy the same bytes, you shouldn't rely on `u.s.a == 1`.
</details>

!!! question "Question 2"
    Why does ¶5 accept only members with a trivial default constructor, rather than implicitly calling the default constructor for any default-constructible type?

<details markdown="1">
<summary>Answer</summary>

An expression that looks like a mere assignment shouldn't secretly run user code. If non-trivial default constructors could be called, `u.s = x;` would run a constructor before the assignment, which might allocate memory or throw, making the evaluation order and exception safety hard to describe. Trivial default construction does nothing, so creating an object out of nothing is indistinguishable from normal default initialization, and it can be done implicitly.
</details>

!!! question "Question 3"
    With `union U { std::string s; int i; };` in C++26, is `U u; u.i = 1;` valid? What happens when `u` goes out of scope afterwards?

<details markdown="1">
<summary>Answer</summary>

Valid. `U`'s default constructor is trivial ([[class.default.ctor#3]] ¶3.4 doesn't look at members for unions), so after `U u;` there is no active member; `u.i = 1` creates an `int` under ¶5. `U`'s destructor is trivial too: the constructor selected for default initialization is trivial, and there is no non-trivial variant member with an initializer. Going out of scope does nothing; the active member is an `int`, so nothing leaks. If `s` were active, `std::destroy_at(&u.s)` would have to be called before leaving the scope. In C++23, `U u;` itself is ill-formed.
</details>
