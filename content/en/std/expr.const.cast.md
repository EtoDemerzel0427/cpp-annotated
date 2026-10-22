---
title: const_cast
summary: "const_cast changes only cv-qualification, for similar object pointers, pointers to data members and the corresponding references; the conversion itself is never undefined behavior, modifying a const object is; this subclause also defines the term casting away constness, which constrains all the other casts."
updated: 2026-10-19
---

!!! tldr
    - `const_cast` only changes `const` and `volatile`; it can remove them or add them, at any level of a multilevel pointer, but it can't change the type itself.
    - It applies to object pointers, pointers to data members and references to objects, not to function pointers or pointers to member functions.
    - The conversion itself is never undefined behavior. Undefined behavior comes from later modifying a const object, and what matters is whether the object itself is const, not whether there is a `const` along the access path.
    - Casting away constness is not only removing a `const` at some level; it also includes conversions like `int**` to `const int**` that add `const` in an unsafe position.
    - Only `const_cast` and C-style casts can cast away constness; `static_cast`, `reinterpret_cast` and `dynamic_cast` can't.

## Is the object const?

<div class="compare" markdown="1">

```cpp run ok
int main() {
  int x = 1;           // x is not const
  const int& cr = x;
  const_cast<int&>(cr) = 2;
  // OK: the modified x is not a const object
  return x == 2 ? 0 : 1;
}
```

```cpp run ub
int main() {
  const int x = 1;     // x is a const object
  const_cast<int&>(x) = 2;
  // UB: modifying a const object
  return x;
}
```

</div>

The `const_cast` is written the same way on both sides, and both conversions are valid. The difference is the object being modified: on the left, `x` is only accessed through a `const int&`, and the object itself is not const; on the right, `x` is a const object, and modifying it is undefined behavior ([[dcl.type.cv]]). In our tests, the program on the right compiled with Clang 23 exits with code 1: the compiler concluded that `x` is always 1 and returned the constant directly.

## Which conversions are possible (¶1–¶4)

¶1 The result has type `T`. If `T` is an lvalue reference to object, the result is an lvalue; if it is an rvalue reference to object, an xvalue; otherwise a prvalue, in which case the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions are applied to the operand first. Except in the case specified by item 4.3, temporary materialization is not applied to the operand. Only the conversions listed below can be performed.

¶1 mentions only references to objects, so `const_cast` can't be used on references to functions. ¶2 is a note: subject to the restrictions of this subclause, an expression can be cast to its own type with `const_cast`.

### Pointers (¶3)

¶3 Let `T1` and `T2` be two [[g:similar-types|similar]] object pointer types or pointer-to-data-member types. If every `P` in their **qualification-decompositions** ([[conv.qual]]) is the same, a prvalue of `T1` can be converted to `T2` with `const_cast`.

A qualification-decomposition breaks a type into the form cv<sub>0</sub> P<sub>0</sub> cv<sub>1</sub> P<sub>1</sub> ⋯ cv<sub>n</sub> U, where each P is a pointer, a pointer to member or an array. For example, `const int* volatile*` decomposes into cv<sub>0</sub> empty, P<sub>0</sub> pointer, cv<sub>1</sub> `volatile`, P<sub>1</sub> pointer, cv<sub>2</sub> `const`, U `int`. Every P being the same means the number and kinds of pointer levels don't change; only the cv at each level differs.

A null pointer converts to a null pointer, and a null member pointer to a null member pointer. Otherwise the result points to the same object as the original pointer (or past its end), or to the same member.

```cpp title="const-cast-ptr.cpp" error
struct S { const int cm = 0; };
void fn();

void t(int** pp, const int* const* cpcp, int* ip, volatile int* vp) {
  int** a = const_cast<int**>(cpcp);           // OK: both levels of const removed
  const int** b = const_cast<const int**>(pp); // OK: const can be added too
  int* c = const_cast<int*>(vp);               // OK: removes volatile
  int S::* m = const_cast<int S::*>(&S::cm);   // OK: pointer to data member
  long* d = const_cast<long*>(ip);             // error: types not similar
  void (*f)() = const_cast<void (*)()>(&fn);   // error: function pointer
  int x = const_cast<int>(*ip);                // error: not a pointer or reference
  (void)a; (void)b; (void)c; (void)m; (void)d; (void)f; (void)x;
}
```

### References (¶4)

¶4 Let `T1` and `T2` be object types. If `T1*` can be converted to `T2*` with `const_cast`, the following three conversions can also be made:

- ¶4.1 an lvalue of `T1` to an lvalue of `T2`: `const_cast<T2&>`;
- ¶4.2 a glvalue of `T1` to an xvalue of `T2`: `const_cast<T2&&>`;
- ¶4.3 if `T1` is a class or array type, a prvalue of `T1` to an xvalue of `T2`: `const_cast<T2&&>`, with temporary materialization applied to the operand first.

The result refers to the same object as the (possibly materialized) operand.

```cpp run title="const-cast-ref.cpp" ok
int main() {
  const int ci = 1;
  const int& cr = ci;
  int& r = const_cast<int&>(cr);    // ¶4.1: the conversion is valid; writing through r is UB
  struct S { int v; };
  S&& s = const_cast<S&&>(S{1});    // ¶4.3: the class prvalue is materialized first
  (void)r;
  return s.v == 1 ? 0 : 1;
}
```

Example 1 in the standard shows an array prvalue:

```cpp title="const-cast-array.cpp"
typedef int* A[3];                // array of 3 int*
typedef const int* const CA[3];   // array of 3 const int* const

auto&& r2 = const_cast<A&&>(CA{});  // OK: the array prvalue is materialized first
```

Per the standard this line is well-formed. Clang 23 rejects it, reporting `const_cast from rvalue to reference type 'A &&'`, which shows Clang hasn't implemented the array prvalue case of item 4.3 yet, so this example has no verdict mark.

¶4.3 applies only to classes and arrays because prvalues of other types carry no cv-qualification at all ([[expr.type]]), so there is nothing to remove. `const_cast<int&&>(5)` is ill-formed.

## The consequences of modification (¶5)

¶5 is a note: depending on the type of the object, a write through the result of a `const_cast` that casts away `const` may produce undefined behavior ([[dcl.type.cv]]). Footnote 50 adds that `const_cast` is not limited to casting away `const`.

The rule in [[dcl.type.cv]] is: modifying a const object (except a `mutable` member) is undefined behavior. By [[basic.type.qualifier]], a **const object** is an object of type `const T`, or a non-`mutable` subobject of such an object; an object created by `new const T` is one too. A `const T&` bound to a non-const object, or a `const T*` pointing to a non-const object, doesn't make the object const.

Making modification of const objects undefined behavior gives implementations two freedoms:

1. Placing const objects in read-only memory. Constant-initialized static `const` objects and string literals are usually in the `.rodata` section, and writing to them causes a segmentation fault.
2. Constant propagation. The compiler can conclude that the value of `const int x = 1;` is always 1 and replace every read with the constant, as in the example at the top.

Undefined behavior is not allowed in constant evaluation, so at compile time the two cases can be told apart exactly:

```cpp title="const-cast-constexpr.cpp" error
constexpr int f() {
  const int x = 1;
  const_cast<int&>(x) = 2;    // modifies a const object
  return x;
}
static_assert(f() == 1);      // error: not a constant expression

constexpr int g() {
  int x = 1;
  const int& r = x;
  const_cast<int&>(r) = 2;    // OK: x is not a const object
  return x;
}
static_assert(g() == 2);      // OK
```

Clang 23's note is `modification of object of const-qualified type 'const int' is not allowed in a constant expression`.

## Casting away constness (¶6, ¶7)

The other named casts all say they can't **cast away constness** ([[g:casts-away-constness]]), and this is where the term is defined.

¶6 Let `T1` and `T2` be different. Take an *n*-level qualification-decomposition of `T1`, and let `T2` have the form cv2<sub>0</sub> P2<sub>0</sub> ⋯ cv2<sub>n</sub> U2. Put the cv of each level of `T2` onto the skeleton of `T1`, giving cv2<sub>0</sub> P1<sub>0</sub> ⋯ cv2<sub>n</sub> U1. If `T1` can't be converted to this type by a qualification conversion, the conversion from `T1` to `T2` casts away constness.

A **qualification conversion** ([[conv.qual]]) is the implicit cv-adding conversion. It can only add cv, and when `const` is added at some level, every level outside it must also be `const`. So there are two ways to cast away constness:

1. actually removing the cv at some level, e.g. `const int*` to `int*`;
2. adding `const` in an unsafe position, e.g. `int**` to `const int**`.

The second looks like adding `const`, but is just as dangerous as the first:

```cpp run title="unsafe-add-const.cpp" ub
const int ci = 0;

int main() {
  int* p = nullptr;
  int** pp = &p;
  auto cpp = const_cast<const int**>(pp);  // requires const_cast
  *cpp = &ci;   // valid: stores a const int* into p
  *p = 1;       // UB: modifies the const object ci through p
}
```

Nothing in the whole sequence visibly casts away `const`, yet a const object ends up modified. In our tests the program crashes at `*p = 1`, because `ci` is in the read-only section. That is exactly why `int**` to `const int**` is not a qualification conversion: it can't happen implicitly, nor with `static_cast`, only with `const_cast`. The safe form adds `const` to the middle level too: `int**` to `const int* const*` is a valid implicit conversion.

¶7 reduces references to pointers: if the conversion from `T1*` to `T2*` casts away constness, then the lvalue reference conversion from an lvalue of `T1` to an lvalue of `T2`, and the rvalue reference conversion from an expression of `T1` to an xvalue of `T2`, also cast away constness.

How the various casts relate to casting away constness:

| Cast | Can cast away constness? | Source |
|---|---|---|
| `const_cast` | Yes | This subclause |
| `static_cast` | No | Every item of [[expr.static.cast]] requires cv not to decrease |
| `reinterpret_cast` | No | [[expr.reinterpret.cast#2]] |
| `dynamic_cast` | No | [[expr.dynamic.cast#1]] |
| C-style cast | Yes, it tries `static_cast` or `reinterpret_cast` followed by `const_cast` | [[expr.cast#4]] |

Concentrating the dangerous act of removing `const` in one conspicuous keyword makes it easy to review and search for.

## Conversions outside const_cast's scope (¶8)

¶8 is a note: some conversions that involve only cv changes can't be done with `const_cast` either.

- Conversions between function pointers are out of scope, because using the resulting values would be undefined behavior.
- For the same reason, conversions between pointers to member functions are out of scope, in particular from a pointer to a `const` member function to a pointer to a non-`const` member function. `void (S::*)() const` and `void (S::*)()` have different function types; they are not similar types differing only in cv.

```cpp title="const-cast-pmf.cpp" error
struct S { void f() const; };

void t() {
  void (S::*p)() const = &S::f;
  auto q = const_cast<void (S::*)()>(p);  // error: pointer to member function
}
```

## Legitimate uses

The first is calling an old interface that isn't const-correct. A C library or old code declares a parameter as `char*` when it should have been `const char*`, and you have confirmed it doesn't write:

```cpp run title="legacy-api.cpp" ok
void legacy_api(char* s) { (void)s; }   // doesn't actually modify s

int main() {
  const char* msg = "hello";
  legacy_api(const_cast<char*>(msg));   // OK: legacy_api doesn't write
}
```

The second is implementing the non-const version in terms of the const version, to avoid duplicate code:

```cpp run title="const-overload.cpp" ok
#include <cstddef>

class Buffer {
  char data_[16]{};
public:
  const char& at(std::size_t i) const {
    // ...complicated bounds checking...
    return data_[i];
  }
  char& at(std::size_t i) {
    // reaching this overload means *this is not a const object
    return const_cast<char&>(static_cast<const Buffer&>(*this).at(i));
  }
};

int main() {
  Buffer b;
  b.at(3) = 'x';
  return b.at(3) == 'x' ? 0 : 1;
}
```

C++23's explicit object parameter (`this auto& self`) offers another way to deduplicate, with no `const_cast` needed.

The third is removing `volatile`, e.g. to hand a `volatile` buffer to a function that doesn't accept `volatile`. Likewise, if the object itself is a volatile object, accessing it through a non-volatile glvalue is undefined behavior ([[dcl.type.cv]]).

## Common misconceptions

!!! pitfall "Casting away const is always safe as long as you don't write"
    That is true of the current code, but "not writing" is often guaranteed only by the called function. Once that function is changed to write, undefined behavior quietly appears.

!!! pitfall "String literals"
    `char* p = const_cast<char*>("abc"); p[0] = 'x';` is undefined behavior: a string literal is a const object, usually in a read-only section, and the program will simply crash at run time.

!!! pitfall "int** to const int** just adds const"
    See the example in paragraph 6: this conversion lets you modify a const object without writing any code that removes `const`, which is why the language counts it as casting away constness.

## Questions

!!! question "Question 1"
    Given `const int* const* p;`, are `const_cast<int* const*>(p)` and `static_cast<const int* const* const>(p)` valid? Does the former cast away constness?

<details markdown="1">
<summary>Answer</summary>

`const_cast<int* const*>(p)` is valid: the two types are similar, every P is the same, and only the `const` of the innermost `int` changes. It casts away constness, because `const int* const*` can't be converted to `int* const*` by a qualification conversion.

`static_cast<const int* const* const>(p)` is also valid. The top-level `const` of a prvalue is discarded, so it is really a conversion to `const int* const*`, i.e. a conversion to the same type, and the implicit conversion sequence required by [[expr.static.cast#5]] exists.
</details>

!!! question "Question 2"
    Given `struct S { mutable int m; int n; }; const S s{};`, what about `const_cast<S&>(s).m = 1;` and `const_cast<S&>(s).n = 1;`?

<details markdown="1">
<summary>Answer</summary>

`s` is a const object, and `s.n` is a non-`mutable` subobject of it, hence also a const object; modifying it is undefined behavior.

`s.m` is a `mutable` member, not a const object ([[basic.type.qualifier]]), so modifying it is valid. In fact no `const_cast` is needed here at all: by [[expr.ref#8.2]], a `mutable` member doesn't inherit the `const` of the object expression, so `s.m = 1;` compiles directly.
</details>

## Summary

!!! summary
    - `const_cast` changes only cv: for similar object pointers and pointers to data members (¶3), and the corresponding lvalue and xvalue references (¶4); class and array prvalues can be materialized first and converted to xvalues (¶4.3).
    - It doesn't apply to pointers of non-similar types, function pointers, pointers to member functions, or types that are neither pointers nor references.
    - The conversion itself is never undefined behavior; modifying a const object is ([[dcl.type.cv]]), and what matters is whether the object itself is const.
    - Casting away constness (¶6, ¶7) means that putting the target's cv onto the source type doesn't give a qualification conversion, covering both removing cv at some level and adding `const` in an unsafe position.
    - Only `const_cast` and C-style casts can cast away constness.
