---
title: optional for reference types
summary: "C++26's optional<T&> is a nullable reference that stores only a pointer: assignment rebinds, every construction that would bind to a temporary is forbidden, const is shallow, and value_or returns by value."
updated: 2026-10-19
---

!!! tldr
    - `optional<T&>` contains only a `T*`, with a null pointer meaning no value; it is always trivially copyable and the same size as a pointer.
    - Assigning to it rebinds: `r = b` makes `r` refer to `b` and does not modify the object `r` previously referred to.
    - Every construction that would bind the reference to a temporary, such as `optional<const int&> r = 42;`, is defined as deleted and is an error at compile time.
    - const is shallow: a `const optional<T&>` can still modify the referenced object; for read-only access write `optional<const T&>`.
    - `value_or` returns `remove_cv_t<T>` by value, so it can never return a dangling reference.

```cpp run ok
#include <cassert>
#include <map>
#include <optional>
#include <string>

std::optional<int&> find(std::map<std::string, int>& m,
                         const std::string& key) {
  auto it = m.find(key);
  if (it == m.end()) return std::nullopt;
  return it->second;            // refers to the element in the map
}

int main() {
  std::map<std::string, int> m{{"a", 1}};
  if (auto r = find(m, "a")) *r = 10;
  assert(m["a"] == 10);
  assert(!find(m, "b"));
}
```

Before C++26 there were only two ways to express a reference that may not exist: a raw pointer `T*`, which says nothing about who owns the object and also permits pointer arithmetic; or `std::optional<std::reference_wrapper<T>>`, which has to be used as `opt->get().member`. Generic code was worse off: in C++23, if the `f` passed to `transform` returned `int&`, the program was simply ill-formed. C++26's [[P2988]] added the partial specialization `optional<T&>`. For the primary template, see [[optional.optional]].

## Inside is a pointer [optional.optional.ref.general]

```cpp
template<class T>
class optional<T&> {
public:
  using value_type = T;
  // …
private:
  T* val = nullptr;                                     // exposition only
};
```

¶1 An `optional<T&>` contains a value if and only if *val* is not a null pointer, and the contained value is a reference to `*`*val*. For the primary template, having a value means whether the union member is active, which involves the object's lifetime; here it only depends on whether a pointer is null. There is no union and no extra `bool`: `sizeof(optional<int&>) == sizeof(int*)`.

¶2 Every `optional<T&>` is a trivially copyable class ([[class.prop]]). This is stated directly as a conclusion: the copy constructor and copy assignment are both `= default` and `noexcept`, the destructor is also `= default`, and copying it means copying a pointer.

The class interface differs from the primary template in a few places:

- `value_type` is `T`, not `T&`;
- there is no `operator=(U&&)`, and no move constructor or move assignment is declared; copying is moving;
- the observers and monadic operations are all `const` member functions returning `T&` or `T*`;
- there is only `iterator`, no `const_iterator`.

## Assignment rebinds [optional.ref.assign]

```cpp run ok
#include <cassert>
#include <optional>
#include <type_traits>

int main() {
  int a = 1, b = 2;
  std::optional<int&> r = a;    // bound to a
  r = b;                        // now bound to b; this is not a = b
  assert(a == 1 && &*r == &b);
  *r = 20;                      // writing through * writes to b
  assert(b == 20);

  r = std::nullopt;             // unbinds; b is unaffected
  assert(!r && b == 20);

  static_assert(sizeof(std::optional<int&>) == sizeof(int*));
  static_assert(std::is_trivially_copyable_v<std::optional<int&>>);
}
```

`optional<T&>` declares only two assignment operators: ¶1 `operator=(nullopt_t)`, which sets *val* to a null pointer, and the defaulted copy assignment. `r = b` compiles because `b` is first implicitly converted to a temporary `optional<int&>` through the non-explicit `optional(U&&)`, and then copy assignment is called, copying the pointer. The result is a **rebind**: `r` now refers to `b`.

For an `optional<T&>` that already has a value, `r = b` has two self-consistent semantics:

| Semantics | What `r = b` does | Rationale |
|---|---|---|
| assign-through | `*r = b` | the same as assignment to `T&` |
| rebind | makes `r` refer to `b` | the meaning of assignment should not depend on run-time state |

The problem with assign-through is that when `r` is empty there is no object to write to, so `r = b` can only bind. The same line of code would modify `a` when `r` has a value and merely bind to `b` when it does not; the meaning of assignment would change with run-time state, and generic code could not predict its behavior. The standard chose rebinding, and simply provides no `operator=(U&&)`, so that assignment has only one meaning: copying another optional.

!!! history "Why it took until C++26"
    The original optional proposal included `optional<T&>`, but it was removed before C++17 because no consensus could be reached in the assign-through versus rebind debate. A later survey of existing optional-reference implementations ([[P1683R0]]) found that they overwhelmingly rebind. Another prerequisite was the type trait `reference_constructs_from_temporary` added in C++23, which made it possible to express "no binding to temporaries" precisely in the library (see the next section).

¶4–6 `emplace(u)` also rebinds, and returns the newly bound reference. Its constraints are that `T&` can be constructed from `U` and would not bind to a temporary; the difference from `r = u` is that it performs direct-initialization, so explicit conversions can be used.

## No binding to temporaries [optional.ref.ctor]

```cpp run error
#include <optional>
#include <string>

int main() {
  int i = 0;
  std::optional<const int&> a = i;              // OK
  std::optional<const int&> b = 42;             // error: deleted
  std::optional<const std::string&> c = "abc";  // error: deleted
  std::optional<const long&> d = i;             // error: deleted
  std::optional<int&> e = 42;                   // error: no viable constructor
}
```

### Binding works the same way as declaring a reference ([optional.ref.expos])

All the binding constructors and `emplace` reduce to an exposition-only helper *convert-ref-init-val*`(u)`. [optional.ref.expos] ¶1 specifies that it creates a variable `r` as if by `T& r(std::forward<U>(u));` and then initializes *val* with `addressof(r)`.

So the binding rules of `optional<T&>` are the rules for declaring a `T&` ([[dcl.init.ref]]), and derived-to-base conversions and conversion functions returning references apply as usual. `addressof` is used rather than `&r` to avoid an overloaded unary `&`.

### Constructing from a value (¶3–7)

```cpp
template<class U>
  constexpr explicit(!is_convertible_v<U, T&>)
  optional(U&& u) noexcept(is_nothrow_constructible_v<T&, U>);
```

¶4 The constraints are that `remove_cvref_t<U>` is neither this optional type nor `in_place_t`, and `is_constructible_v<T&, U>`. The `explicit` condition is `!is_convertible_v<U, T&>`: if it can bind implicitly, it can be constructed implicitly.

¶7 If `reference_constructs_from_temporary_v<T&, U>` is true, this constructor is defined as deleted. This type trait ([[meta.rel]]) determines whether initializing a `T&` with an expression of type `U` would bind the reference to a temporary object. `b`, `c` and `d` in the example above all would: `42` is a prvalue, `"abc"` first needs a temporary `string` to be constructed, and converting `int` to `long` also produces a temporary.

The core language allows `const T&` to bind to a temporary and extend its lifetime, but only when it binds directly to a reference variable ([[class.temporary]]). After passing through the optional constructor's parameter, the temporary is destroyed at the end of the full-expression, and the `optional<const T&>` is guaranteed to dangle. So the standard forbids these constructions outright.

The error for `e` in the example is of a different nature: `int&` cannot bind to a prvalue, `is_constructible_v<int&, int>` is false, and the constructor does not participate in overload resolution at all. The constructors for `b`, `c` and `d` participate in overload resolution, are selected, and then cause an error because they are deleted.

"No binding to temporaries" is written as deletion rather than as *Constraints* to block any escape route. If the constructor were merely removed from the candidates, overload resolution might find another viable path and compile silently; a deleted function, once selected as the best match, always causes an error. The reference-member construction of `std::pair` and `std::tuple` is specified the same way ([[pairs]], [[tuple]]).

¶1 `optional(in_place_t, Arg&& arg)` accepts only one argument, since a reference can only be bound from one thing. Both of its conditions are *Constraints*: `is_constructible_v<T&, Arg>` is true and `reference_constructs_from_temporary_v<T&, Arg>` is false. `in_place` construction is always invoked explicitly, so there is no risk of another candidate taking its place.

### Constructing from another optional (¶8–19)

The primary template has only two converting constructors, `const optional<U>&` and `optional<U>&&`; `optional<T&>` has four: `optional<U>&`, `const optional<U>&`, `optional<U>&&` and `const optional<U>&&`. This is because the constness and value category of the source object directly determine whether binding is possible: from `optional<int>&` you can get an `int&`, from `const optional<int>&` only a `const int&`.

Taking the `optional<U>&` version as an example, the constraints in ¶8 are:

- ¶8.1 `remove_cv_t<T>` is not `optional<U>`. If `T` is itself `optional<U>`, for example constructing `optional<optional<int>&>` from `optional<int>&`, what is wanted is to bind to that optional object itself, which is left to `optional(U&&)`;
- ¶8.2 `T&` is not `U`; otherwise the source is an `optional<T&>` of the same type, which is left to the copy constructor;
- ¶8.3 `is_constructible_v<T&, U&>`.

¶9 If there is a value, it calls *convert-ref-init-val*`(rhs.operator*())`, that is, it binds to the value inside the source optional. ¶10 If this would bind to a temporary, the constructor is defined as deleted.

```cpp run ok
#include <cassert>
#include <optional>

struct Base { int id = 1; };
struct Derived : Base { };

int f() { return 7; }

int main() {
  std::optional<Derived> od = Derived{};
  std::optional<Base&> rb = od;   // binds to the Derived inside od
  assert(&*rb == &*od);

  std::optional<int(&)()> fr = f; // function references work too
  assert((*fr)() == 7);
}
```

Whether `rb` is valid depends entirely on whether `od`'s contained value is still alive:

```cpp run ub
#include <optional>

int main() {
  std::optional<int> src = 1;
  std::optional<int&> r = src;    // refers to src's contained value
  src.reset();                    // the contained value's lifetime ends
  return *r;                      // UB: r still has a value, but it dangles
}
```

`r.has_value()` is still true: `optional<T&>` only looks at its own pointer and does not know the source object has been destroyed. This is the same as a dangling raw pointer; `reference_constructs_from_temporary` can only stop temporaries, not named objects that are destroyed too early.

The rvalue versions, however, do stop one common mistake. In `optional<const int&> r = make_opt();` (where `make_opt` returns `optional<int>`), `U = int`, `reference_constructs_from_temporary_v<const int&, int>` is true, and the constructor is deleted, so taking a reference out of a temporary optional is rejected at compile time.

!!! impl "libc++"
    libc++ 23 writes two declarations for each constructor that is defined as deleted, distinguished by mutually exclusive `requires` clauses: one with a normal implementation and one `= delete`. The storage is a single pointer member, and `__convert_init_ref_val` corresponds to *convert-ref-init-val* in the specification. In our tests, libc++ 23 in C++26 mode defines `__cpp_lib_optional` as `202506L`, which includes `optional<T&>`.

## const is shallow [optional.ref.observe]

```cpp run ok
#include <cassert>
#include <optional>
#include <string>
#include <type_traits>

struct Widget { std::string name; };

int main() {
  Widget w{"w"};
  const std::optional<Widget&> cr = w;  // the optional itself is const
  cr->name = "changed";                 // the referenced object is not
  assert(w.name == "changed");

  std::optional<Widget&> none;
  Widget fallback{"fb"};
  auto r = none.or_else(
      [&] { return std::optional<Widget&>(fallback); });
  assert(&*r == &fallback);

  auto len = cr.transform([](Widget& x) { return x.name.size(); });
  static_assert(std::is_same_v<decltype(len),
                               std::optional<std::size_t>>);
  assert(*len == 7);
}
```

The observers are all `const` member functions and return `T&` rather than `const T&`:

```cpp
constexpr T* operator->() const noexcept;
constexpr T& operator*()  const noexcept;
constexpr T& value()      const;
```

This is **shallow const**, the same as for pointers, `std::span` and `std::reference_wrapper`: `const` restricts what this optional refers to, not the referenced object. For read-only access use `optional<const T&>`.

¶1–4 `operator->` and `operator*` have the hardened precondition `has_value()`. As with the primary template, a hardened implementation checks and terminates, and in a non-hardened implementation violating it is {{ub}}, here a null pointer dereference. ¶5–6 `operator bool` and `has_value()` return whether *val* is non-null. ¶7 `value()` is equivalent to `return has_value() ? *val : throw bad_optional_access();` and is deleted in a freestanding implementation.

### `value_or` returns by value (¶8–12)

```cpp
template<class U = remove_cv_t<T>>
  constexpr remove_cv_t<T> value_or(U&& u) const;
```

¶9–11 Let `X` be `remove_cv_t<T>`; the effect is equivalent to `has_value() ? *val : static_cast<X>(std::forward<U>(u))`. ¶10 requires that `X` be constructible from `T&` and that `U` be implicitly convertible to `X` (*Mandates*).

Returning `T&` might seem more natural, but the fallback value is almost always a temporary, as in `r.value_or(0)` or `name.value_or("unknown")`. If it returned `T&`, the reference would have to bind to that argument, and `const int& x = r.value_or(0);` would dangle immediately. Returning by value gives up the ability to return a reference in exchange for `value_or` never causing a dangling reference. When you need a reference, or a fallback reference, write `r ? *r : fallback`, or use `or_else` to return another `optional<T&>`.

```cpp run error
#include <optional>
int main() {
  int a = 1;
  std::optional<int&> r = a;
  int& x = r.value_or(a);   // error: value_or returns an int prvalue
}
```

¶8 `value_or` is callable only when `T` is a non-array object type (*Constraints*). ¶12 If `T` is an array or a non-object type (such as a function type), the return type is unspecified. Note 1 explains that this avoids making the declaration itself ill-formed: `remove_cv_t<int[3]>` cannot be a function's return type, so if written as is, `optional<int(&)[3]>` would fail as soon as it is instantiated, even if `value_or` is never called. libc++ writes the return type as `decay_t<T>`, which is `remove_cv_t<T>` for non-array object types and decays to a pointer for arrays and functions, so the declaration is always valid.

## Monadic operations [optional.ref.monadic]

The three monadic operations are all `const` members with a single overload each:

- ¶1–3 `and_then`: let `U` be `invoke_result_t<F, T&>`; `remove_cvref_t<U>` must be a specialization of `optional`; if there is a value it returns `invoke(f, *val)`, otherwise an empty `remove_cvref_t<U>`.
- ¶4–6 `transform`: let `U` be `remove_cv_t<invoke_result_t<F, T&>>`; it must be a valid contained type and `U u(invoke(f, *val));` must be well-formed, with no movability required; it returns `optional<U>`. When `f` returns a reference, the result is another `optional<X&>`, so projections can be chained, for example `person.transform(&Person::address).transform(&Address::city)`.
- ¶7–9 `or_else`: requires `F` to be callable with no arguments (*Constraints*) and `f()` to return this `optional<T&>` (*Mandates*); if there is a value it returns an optional referring to the same object, otherwise `f()`.

!!! lawyer "The synopsis and the detailed specification disagree"
    The class synopsis in [optional.optional.ref.general] gives the return type of `transform` as `optional<invoke_result_t<F, T&>>`, while the detailed declaration in [optional.ref.monadic] is `optional<remove_cv_t<invoke_result_t<F, T&>>>`. The two differ when `f` returns a cv-qualified prvalue type such as `const int`. This looks like an editorial issue left over from the merge. libc++ 23 implements the detailed declaration.

## swap, iterators and reset

[optional.ref.swap] ¶1 `swap` is equivalent to `std::swap(val, rhs.val)`: it only swaps two pointers and is always `noexcept`. That is why the constraint on the non-member `swap` in [[optional]] has an `is_reference_v<T> ||` branch and does not require `T` to be swappable.

[optional.ref.iterators] {{c++26}} `iterator`, `begin` and `end` exist only when `T` is an object type and not an array of unknown bound (¶3, ¶5). ¶1 The iterator models `contiguous_iterator`, with reference type `T&`; ¶4 and ¶6: if there is a value, `begin()` points to `*`*val*, and `end()` is `begin() + has_value()`. The iterators point to an external object and do not depend on whether the optional itself is still alive, so [[optional]] declares `enable_borrowed_range<optional<T&>>` to be true. In our tests, libc++ 23, as with the primary template, only provides the iterators with `-fexperimental-library`.

[optional.ref.mod] `reset()` sets *val* to a null pointer.

## Comparison and hash

`optional<T&>` has no comparison operators of its own. The comparison function templates in [[optional]] take `optional<T>` parameters and apply equally to `T&`; they compare `*x == *y`, that is, the referenced values, not the addresses:

```cpp run ok
#include <cassert>
#include <optional>

int main() {
  int x = 3, y = 3;
  std::optional<int&> px = x, py = y;
  assert(px == py);           // equal values
  assert(&*px != &*py);       // not referring to the same object
}
```

This is the opposite of pointers. To check whether they refer to the same object, compare `&*x == &*y`, after making sure both sides have values.

[optional.hash] specifies that `hash<optional<T>>` is enabled if and only if `hash<remove_const_t<T>>` is enabled. For `optional<int&>`, this requires `hash<int&>` to be enabled, and the standard does not enable `hash` for reference types, so by the letter of the rule `hash<optional<T&>>` is disabled; see [[optional]].

## Questions

!!! question "Question 1"
    `optional<T&>` has no `operator=(U&&)`, so why does `r = b;` compile? If `T&` can only be constructed explicitly from `U` (for example, `U` has an `explicit operator T&()`), does `r = u;` still compile? How should it be written?

<details markdown="1">
<summary>Answer</summary>

In `r = b`, `b` is implicitly converted to a temporary `optional<T&>` through the non-explicit `optional(U&&)`, which then matches the copy assignment `operator=(const optional&)`. If the conversion is explicit, `optional(U&&)` is `explicit(true)` and cannot be used to initialize the assignment operator's parameter, so `r = u` has no viable function. You can write `r = std::optional<T&>(u);` or `r.emplace(u);`. `emplace` goes through `T& r(std::forward<U>(u));` in *convert-ref-init-val*, which is direct-initialization, so explicit conversion functions can be used.
</details>

!!! question "Question 2"
    In `std::optional<const std::string&> name = get_name();`, what happens if `get_name()` returns `std::string`? What if it returns `const std::string&`?

<details markdown="1">
<summary>Answer</summary>

When it returns a `std::string` prvalue, `U = std::string`, `reference_constructs_from_temporary_v<const std::string&, std::string>` is true, `optional(U&&)` is deleted, and compilation fails; this is exactly the dangling case the rule is meant to catch. When it returns `const std::string&`, `U = const std::string&`, the reference binds directly to an lvalue, no temporary is involved, and it compiles. Whether the result is valid then depends on the reference returned by `get_name()` itself, which the standard library has no way to check.
</details>
